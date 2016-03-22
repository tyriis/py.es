# Copyright © 2015 STRG.AT GmbH, Vienna, Austria
#
# This file is part of the The SCORE Framework.
#
# The SCORE Framework and all its parts are free software: you can redistribute
# them and/or modify them under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation which is in the
# file named COPYING.LESSER.txt.
#
# The SCORE Framework and all its parts are distributed without any WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. For more details see the GNU Lesser General Public
# License.
#
# If you have not received a copy of the GNU Lesser General Public License see
# http://www.gnu.org/licenses/.
#
# The License-Agreement realised between you as Licensee and STRG.AT GmbH as
# Licenser including the issue of its valid conclusion and its pre- and
# post-contractual effects is governed by the laws of Austria. Any disputes
# concerning this License-Agreement including the issue of its valid conclusion
# and its pre- and post-contractual effects are exclusively decided by the
# competent court, in whose district STRG.AT GmbH has its registered seat, at
# the discretion of STRG.AT GmbH also the competent court, in whose district the
# Licensee has his registered seat, an establishment or assets.

from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import NotFoundError
from score.init import ConfiguredModule, parse_list, parse_bool, extract_conf
from sqlalchemy import event
from time import time
import inspect
import logging
from functools import partial


log = logging.getLogger(__name__)

defaults = {
    'ctx.member': 'es',
}


def init(confdict, db, ctx=None):
    """
    Initializes this module acoording to :ref:`our module initialization
    guidelines <module_initialization>` with the following configuration keys:

    :confkey:`args.hosts`
        A list of hosts (as read by :func:`score.init.parse_list`) to pass to
        the :class:`Elasticsearch <elasticsearch.Elasticsearch>` constructor.

    :confkey:`args.*`
        Any other arguments to be passed to the :class:`Elasticsearch
        <elasticsearch.Elasticsearch>` constructor.

    :confkey:`index` :default:`score`
        The index to use in all operations.

    :confkey:`ctx.member` :default:`es`
        The name of the :term:`context member`, that should be registered with
        the configured :mod:`score.ctx` module (if there is one). The default
        value allows one to conveniently query the index:

        >>> for knight in ctx.es.query(User, 'name:sir*')
        ...     print(knight.name)
    """
    conf = defaults.copy()
    conf.update(confdict)
    kwargs = extract_conf(confdict, 'args.')
    if 'hosts' in kwargs:
        kwargs['hosts'] = parse_list(kwargs['hosts'])
    if 'verify_certs' in kwargs:
        kwargs['verify_certs'] = parse_bool(kwargs['verify_certs'])
    if 'use_ssl' in kwargs:
        kwargs['use_ssl'] = parse_bool(kwargs['use_ssl'])
    es = Elasticsearch(**kwargs)
    if 'index' not in confdict:
        confdict['index'] = 'score'
    es_conf = ConfiguredEsModule(db, es, confdict['index'])
    to_insert = []
    to_delete = []

    @event.listens_for(db.Session, 'before_flush')
    def before_flush(session, flush_context, instances):
        """
        Stores the list of new and altered objects in ``to_insert``, and
        deleted objects in ``to_delete``. The actual storing can only be done
        *after* the flush operation (in ``after_flush``, below), since new
        objects don't have an id at this point. But we cannot move the whole
        logic into the ``after_flush``, since we might miss the optional
        *instances* argument to this function.
        """
        nonlocal to_insert, to_delete
        to_insert = []
        to_delete = []
        for obj in session.new:
            if not instances or obj in instances:
                if es_conf.get_es_class(obj) is not None:
                    to_insert.append(obj)
        for obj in session.dirty:
            if not session.is_modified(obj):
                # might actually be unaltered, see docs of Session.dirty:
                # http://docs.sqlalchemy.org/en/latest/orm/session_api.html#sqlalchemy.orm.session.Session.dirty
                continue
            if not instances or obj in instances:
                if es_conf.get_es_class(obj) is not None:
                    to_insert.append(obj)
        for obj in session.deleted:
            if not instances or obj in instances:
                if es_conf.get_es_class(obj) is not None:
                    to_delete.append(obj)

    @event.listens_for(db.Session, 'after_flush')
    def after_flush(session, flush_context):
        for obj in to_insert:
            es_conf.insert(obj)
        for obj in to_delete:
            es_conf.delete(obj)
    if ctx and conf['ctx.member'] not in (None, 'None'):
        ctx.register(conf['ctx.member'], lambda ctx: CtxProxy(es_conf, ctx))
    return es_conf


class ConfiguredEsModule(ConfiguredModule):
    """
    This module's :class:`configuration class
    <score.init.ConfiguredModule>`.
    """

    def __init__(self, db, es, index):
        self.db = db
        self.es = es
        self.index = index
        self._converters = {}

    def insert(self, object_):
        """
        Inserts an *object_* into the index.
        """
        body = self._object2json(object_)
        doc_type = body['_type']
        del body['_id']
        del body['_type']
        self.es.index(
            index=self.index,
            doc_type=doc_type,
            body=body,
            id=object_.id)

    def _object2json(self, object_):
        """
        Converts given *object_* to the JSON representation required for
        indexing.
        """
        cls = object_.__class__
        if cls not in self._converters:
            self._converters[cls] = self._mkconverter(cls)
        return self._converters[cls](object_)

    def _mkconverter(self, cls):
        """
        Generates a function for efficiently converting an object of given class
        *cls* to its json representation as returned by :meth:`._object2json`.
        """
        es_cls = self.get_es_class(cls)
        bodytpl = {
            'class': [],
            'concrete_class': cls.__score_db__['type_name'],
            '_type': es_cls.__score_db__['type_name'],
        }
        getters = {}
        while cls:
            bodytpl['class'].append(cls.__score_db__['type_name'])
            if hasattr(cls, '__score_es__'):
                for member in cls.__score_es__:
                    if member in bodytpl:
                        continue
                    converter = None
                    if '__convert__' in cls.__score_es__[member]:
                        converter = cls.__score_es__[member]['__convert__']
                    getters[member] = self.__mkmembergetter(member, converter)
            if cls == es_cls:
                break
            cls = cls.__score_db__['parent']

        def converter(object_):
            body = bodytpl.copy()
            body['_id'] = object_.id
            for member, getter in getters.items():
                body[member] = getter(object_)
            return body
        return converter

    def __mkmembergetter(self, member, converter=None):
        """
        Helper function for _mkconverter: Will return a function that retrieves
        a member value and optionally converts it with given converter.
        """
        if converter is None:
            return lambda object_: getattr(object_, member)
        if len(inspect.getargspec(converter).args) == 2:
            def getter(object_):
                return converter(getattr(object_, member), object_)
        else:
            def getter(object_):
                return converter(getattr(object_, member))
        return getter

    def delete(self, object_):
        """
        Removes an *object_* from the index.
        """
        es_cls = self.get_es_class(object_)
        try:
            self.es.delete(
                index=self.index,
                doc_type=es_cls.__score_db__['type_name'],
                id=object_.id)
        except NotFoundError:
            pass

    def query(self, ctx, class_, query, *,
              analyze_wildcard=False, offset=0, limit=10):
        """
        Executes a lucene *query* on the index and yields a list of objects of
        given *class_*, retrieved from the database. It is also possible to
        provide multiple classes, in which case the same query will be performed
        on `multiple types at once`_.

        The *query* can be provided as a string, or as a `query DSL`_. The
        parameter *analyze_wildcard* wildcard is passed to
        :meth:`elasticsearch.Elasticsearch.search`, whereas *offset* and *limit*
        are mapped to *from_* and *size* respectively.

        .. _query DSL: http://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html
        .. _multiple types at once: https://www.elastic.co/guide/en/elasticsearch/guide/master/multi-index-multi-type.html
        """
        if isinstance(class_, type):
            classes = [class_]
        else:
            classes = class_
        doctypes = []
        doctype2class = {}
        for class_ in classes:
            typename = self.get_es_class(class_).__score_db__['type_name']
            doctype2class[typename] = class_
            doctypes.append(typename)
        kwargs = {
            'index': self.index,
            'analyze_wildcard': analyze_wildcard,
            'fields': '_id',
            'doc_type': ','.join(doctypes),
            'from_': offset,
            'size': limit,
        }
        if isinstance(query, str):
            kwargs['q'] = query
        else:
            kwargs['body'] = {'query': query}
        session = getattr(ctx, self.db.ctx_member)
        result = self.es.search(**kwargs)
        current_class = None
        ids = []
        for hit in result['hits']['hits']:
            class_ = doctype2class[hit['_type']]
            if class_ != current_class:
                if current_class:
                    yield from session.by_ids(current_class, ids)
                current_class = class_
                ids = []
            ids.append(int(hit['_id']))
        yield from session.by_ids(current_class, ids)

    def get_es_class(self, object_):
        """
        Returns the :term:`top-most es class` of an *object_*, which must
        either be a database class, or an object thereof.
        """
        if not isinstance(object_, type):
            cls = object_.__class__
        else:
            cls = object_
        if not hasattr(self, '_es_classes'):
            self._es_classes = {}
        if cls in self._es_classes:
            return self._es_classes[cls]
        initial_class = cls
        result = None
        if hasattr(cls, '__score_es__'):
            result = cls
        while cls.__score_db__['parent']:
            if hasattr(cls, '__score_es__'):
                result = cls
            cls = cls.__score_db__['parent']
        self._es_classes[initial_class] = result
        return result

    def classes(self):
        """
        Provides a list of :term:`top-most classes <top-most es class>` with a
        __score_es__ declaration.
        """
        if hasattr(self, '_classes'):
            return self._classes
        self._classes = []

        def recurse(cls):
            if hasattr(cls, '__score_es__'):
                self._classes.append(cls)
                return
            for c in cls.__subclasses__():
                recurse(c)
        recurse(self.db.Base)
        return self._classes

    def refresh(self, ctx):
        """
        Re-inserts every object into the lucene index. Note that this operation
        might take a very long time, depending on the number of objects.
        """
        def generator():
            session = getattr(ctx, self.db.ctx_member)
            for cls in self.classes():
                start = time()
                log.debug('indexing %s' % cls)
                for obj in session.query(cls).yield_per(100):
                    body = self._object2json(obj)
                    body['_index'] = self.index
                    yield body
                log.debug('indexed %s in %fs' % (cls, time() - start))
        helpers.bulk(self.es, generator())

    def destroy(self):
        """
        Completely deletes the whole index.
        """
        self.es.indices.delete(index=self.index, ignore=404)

    def create(self, destroy=True):
        """
        Creates the elasticsearch index and registers all mappings. If the
        parameter *destroy* is left at its default value, the index will be
        :meth:`destroyed <.destroy>` first.

        If the index is not deleted first, this function will raise an exception
        if the new mapping contradicts an existing mapping in the index.
        """
        if destroy:
            self.destroy()
        self.es.indices.create(index=self.index, ignore=400)
        for cls in self.classes():
            key = cls.__score_db__['type_name']
            mapping = {}
            mapping[key] = {'properties': {}}
            mapping[key]['_source'] = {'enabled': False}

            def recurse(cls):
                if hasattr(cls, '__score_es__'):
                    for member in cls.__score_es__:
                        definition = cls.__score_es__[member].copy()
                        definition.pop('__convert__', None)
                        mapping[key]['properties'][member] = definition
                for c in cls.__subclasses__():
                    recurse(c)
            recurse(cls)
            mapping[key]['properties']['class'] = {
                'type': 'string',
                'index': 'not_analyzed'}
            mapping[key]['properties']['concrete_class'] = {
                'type': 'string',
                'index': 'not_analyzed'}
            self.es.indices.put_mapping(
                index=self.index,
                doc_type=key,
                body=mapping)


class CtxProxy:
    """
    Wrapper for the ConfiguredEsModule, which stores a reference to a context
    object and passes that object transparently to the functions requiring a
    context. This avoids duplicating the *ctx* parameter when accessing the
    configuration through the context object itself. In other words: you won't
    need to do the following when using this class:

    >>> ctx.es.query(ctx, User, ...

    You can instead omit the second context object:

    >>> ctx.es.query(User, ...

    """

    def __init__(self, conf, ctx):
        self._conf = conf
        self._ctx = ctx

    def __getattr__(self, attr):
        result = getattr(self._conf, attr)
        if attr in ('query', 'refresh'):
            result = partial(result, self._ctx)
        return result
