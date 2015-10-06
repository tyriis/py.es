.. _es_glossary:

.. glossary::

    top-most es class
        The first class within :mod:`score.db`'s class hierarchy — as defined
        by the classes' :ref:`__score_db__['base'] <db_config_member>` — that
        has a class member called ``__score_es__``. 

        Example: Given the class hierarchy in the next few lines, the class
        ``X`` would be considered the top-most es class in ``Foo``'s class
        hierarchy.

        .. code-block:: python
            :linenos:

            class A(Base):
                pass

            class B(A):
                pass

            class X(B):
                __score_es__ = {
                    'name': {'type': 'string'}
                }
                name = Column(String)

            class Foo(X)
                __score_es__ = {
                    'user_id': {'type': 'integer'}
                }
                user_id = Column(Integer, ForeignKey('_user.id'))


