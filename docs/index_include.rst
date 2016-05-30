.. module:: score.es
.. role:: confkey
.. role:: confdefault

********
score.es
********

Aim of this module is to provide automated management of the contents of an
elasticsearch index and a convenient access, that integrates seamlessly with
the :mod:`score.db` module.


Quickstart
==========

The module will automatically detect classes with the special member
``__score_es__``. This dictionary must contain a mapping of real member names
to an elasticsearch mapping definition:

.. code-block:: python

    class User(Base):
        __score_es__ = {
            'name': {'type': 'string', 'index': 'not_analyzed'},
        }
        name = Column(String)

    class Text(Base):
        __score_es__ = {
            'title': {'type': 'string'},
            'body': {'type': 'string', 'term_vector': 'with_offsets'},
        }
        title = Column(String(200))
        body = Column(String)

    class SillyText(Text):
        pass

Create your elasticsearch index automatically after updating all models:

>>> score.es.create()

You can now use the :term:`context member` *es* to query your index:

>>> for text in ctx.es.query(Text, 'title:dead AND title:parrot'):
...     print('{text.id}: {text.title}'.format(text=text))

Configuration
=============

.. autofunction:: score.es.init

Details
=======

Automatic Fields
----------------

Whenever objects of managed classes are stored in the configured database, they
are also automatically added to the configured elasticsearch index. The
following document properties will be added automatically:

- ``_id``: This is equal to the id of the object in the database
- ``_type``: Equal to the name of the :term:`top-most es class`, i.e. ``text``.
  The name is the same name defined in the database as
  :ref:`__score_db__['type_name'] <db_config_member>`
- ``class``: A value appearing multiple times, once for each class upwards in
  the class hierarchy toward the :term:`top-most es class`, i.e. ``silly_text``
  and ``text``. The names are those described for ``_type``, above.
- ``concrete_class``: Appears only once, and corresponds to the class name of
  the object, i.e. ``silly_text`` only. The names are those described for
  ``_type``, above.

Apart from the additional members, the following deviations from
elasticsearch's default behaviour automatically apply to all mappings:

- ``_source`` will be disabled, since all member values will be retrieved from
  the database. It is possible to store single members using the field property
  store_, if necessary.

.. _store: http://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-core-types.html#string


Conversion
----------

It is possible to provide a conversion function for member values. The
function may accept either one or two parameters. The first value is always the
value to convert, whereas the second value will be the object instance:

.. code-block:: python

    class L33tText(SillyText):
        __score_es__ = {
            'body': {'type': 'string', 'term_vector': 'with_offsets',
                     '__convert__': lambda b: b.replace('e', '3')},
        }

    class VeryShortText(SillyText):
        __score_es__ = {
            'body': {'type': 'string', 'term_vector': 'with_offsets',
                     '__convert__': lambda b, text: text.title},
        }

API
===

.. autofunction:: score.es.init

.. autoclass:: score.es.ConfiguredEsModule

    .. attribute:: index

        The index to operate on. This will be passed as the ``index`` keyword
        argument to almost every Elasticsearch function.

    .. attribute:: es

        The configured :class:`elasticsearch.Elasticsearch` instance. Do not
        forget to use the configured :attr:`.index` value when operating on
        this directly.

    .. automethod:: score.es.ConfiguredEsModule.destroy

    .. automethod:: score.es.ConfiguredEsModule.create

    .. automethod:: score.es.ConfiguredEsModule.refresh

    .. automethod:: score.es.ConfiguredEsModule.insert

    .. automethod:: score.es.ConfiguredEsModule.delete

    .. automethod:: score.es.ConfiguredEsModule.query

    .. automethod:: score.es.ConfiguredEsModule.classes

    .. automethod:: score.es.ConfiguredEsModule.get_es_class
