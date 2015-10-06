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

"""
This package :ref:`integrates <framework_integration>` the module with
pyramid_.

.. _pyramid: http://docs.pylonsproject.org/projects/pyramid/en/latest/
"""


def init(confdict, configurator, db_conf, ctx_conf=None):
    """
    Apart from calling the :func:`base initializer <score.db.init>`, this
    function will also register a :ref:`reified request method
    <pyramid:adding_request_method>` called ``es`` on all :ref:`Request
    <pyramid:request_module>` objects that provides the configured module. This
    allows one to conveniently query the index:

    >>> for knight in request.es.query(User, 'name:sir*')
    ...     print(knight.name)
    """
    import score.es
    es_conf = score.es.init(confdict, db_conf, ctx_conf)
    if not ctx_conf:
        def es(request):
            return es_conf
        configurator.add_request_method(es, reify=True)
    return es_conf
