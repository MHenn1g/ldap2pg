from __future__ import unicode_literals

from collections import OrderedDict
import logging

from .format import collect_fields, AttributesMap, FormatList
from .psql import Query
from .utils import dedent, unicode


logger = logging.getLogger(__name__)


class Role(object):
    __slots__ = (
        'comment',
        'lname',
        'uname',
        'members',
        'name',
        'options',
        'parents',
    )

    def __init__(self, name, options=None, members=None, parents=None,
                 comment=None):
        self.name = name
        self.lname = name.lower()
        self.uname = name.upper()
        self.members = members or []
        self.options = RoleOptions(options or {})
        self.parents = parents or []
        self.comment = comment

    def __eq__(self, other):
        return self.name == unicode(other)

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.name)

    def __str__(self):
        return self.name

    def __lt__(self, other):
        return unicode(self) < unicode(other)

    @classmethod
    def from_row(cls, name, members=None, *row):
        self = Role(name=name, members=list(filter(None, members or [])))
        options_num = len(RoleOptions.SUPPORTED_COLUMNS)
        options_values = row[:options_num]
        self.options.update_from_row(options_values)
        comment = row[options_num:]
        if comment:
            self.comment = comment[0]
        self.options.fill_with_defaults()
        return self

    def create(self):
        yield Query(
            'Create %s.' % (self.name,),
            None,
            dedent("""\
            CREATE ROLE "{role}" WITH {options};
            COMMENT ON ROLE "{role}" IS '{comment}';
            """).format(
                role=self.name, options=self.options,
                comment=self.comment or '')
        )
        if self.members:
            yield Query(
                'Add %s members.' % (self.name,),
                None,
                'GRANT "%(role)s" TO %(members)s;' % dict(
                    members=", ".join(map(lambda x: '"%s"' % x, self.members)),
                    role=self.name,
                ),
            )

    def rename(self, other):
        if self.name != other.name:
            yield Query(
                'Rename %s to %s.' % (self.name, other.name),
                None,
                """ALTER ROLE "%(old)s" RENAME TO "%(new)s";""" % dict(
                    old=self.name, new=other.name,
                ),
            )

    def alter(self, other):
        # Yields SQL queries to reach other state.

        if self.options != other.options:
            yield Query(
                'Update options of %s.' % (other.name,),
                None,
                """ALTER ROLE "{role}" WITH {options};""".format(
                    role=other.name, options=other.options)
            )

        if self.members != other.members:
            renamed = set([
                name for name in other.members
                if name.lower() in self.members
            ])
            renamed_lower = set([name.lower() for name in renamed])
            missing = set(other.members) - renamed - set(self.members)
            if missing:
                logger.debug(
                    "Role %s miss members %s.",
                    other.name, ', '.join(missing)
                )
                yield Query(
                    'Add missing %s members.' % (other.name,),
                    None,
                    "GRANT \"%(role)s\" TO %(members)s;" % dict(
                        members=", ".join(map(lambda x: '"%s"' % x, missing)),
                        role=other.name,
                    ),
                )
            spurious = set(self.members) - renamed_lower - set(other.members)
            if spurious:
                yield Query(
                    'Delete spurious %s members.' % (other.name,),
                    None,
                    "REVOKE \"%(role)s\" FROM %(members)s;" % dict(
                        members=", ".join(map(lambda x: '"%s"' % x, spurious)),
                        role=other.name,
                    ),
                )

        if self.comment != other.comment:
            yield Query(
                'Update comment on %s.' % (other.name,),
                None,
                """COMMENT ON ROLE "{role}" IS '{comment}';""".format(
                    role=other.name,
                    comment=other.comment or '',
                )
            )

    def drop(self, databases=None, me=None):
        yield Query(
            'Terminate running sessions for %s.' % self.name,
            None, dedent("""\
            SELECT pg_terminate_backend(pid)
            FROM pg_catalog.pg_stat_activity
            WHERE usename = '%s';
            """) % self.name,
        )
        databases = databases or []
        for db in databases:
            fmtkw = dict(owner=db.owner, role=self.name, me=me)
            queries = []
            if me in self.parents:
                # Break membership loop before granting.
                queries.append("""REVOKE "%(me)s" FROM "%(role)s";""")
                self.parents.remove(me)

            if me not in self.members:
                # Inherit from target role to reassign even if non-superuser.
                queries.append("""GRANT "%(role)s" TO %(me)s;""")
                self.members.append(me)

            queries.append("""REASSIGN OWNED BY "%(role)s" TO "%(owner)s";""")
            queries.append("""DROP OWNED BY "%(role)s";""")

            yield Query(
                "Reassign %s's objects and purge ACL in %s." % (self.name, db),
                db.name, '\n'.join(queries) % fmtkw,
            )

        yield Query(
            'Drop %s.' % (self.name,),
            None,
            "DROP ROLE \"%(role)s\";" % dict(role=self.name),
        )

    def merge(self, other):
        self.options.update(other.options)
        self.members += other.members
        self.parents += other.parents
        return self

    def rename_members(self, renamed):
        # renamed: oldname -> newrole.
        # Apply renaming to members.
        for i, oldname in enumerate(self.members[:]):
            try:
                oldname = renamed[oldname].name
            except KeyError:
                continue
            else:
                self.members[i] = oldname


class RoleOptions(dict):
    COLUMNS = OrderedDict([
        # column: (option, default)
        ('rolbypassrls', ('BYPASSRLS', False)),
        ('rolcanlogin', ('LOGIN', False)),
        ('rolcreatedb', ('CREATEDB', False)),
        ('rolcreaterole', ('CREATEROLE', False)),
        ('rolinherit', ('INHERIT', True)),
        ('rolreplication', ('REPLICATION', False)),
        ('rolsuper', ('SUPERUSER', False)),
    ])

    SUPERONLY_COLUMNS = ['rolsuper', 'rolreplication', 'rolbypassrls']
    SUPPORTED_COLUMNS = list(COLUMNS.keys())

    @classmethod
    def supported_options(cls):
        return [
            o for c, (o, _) in cls.COLUMNS.items()
            if c in cls.SUPPORTED_COLUMNS
        ]

    COLUMNS_QUERY = dedent("""
    SELECT array_agg(attrs.attname)
    FROM pg_catalog.pg_namespace AS nsp
    JOIN pg_catalog.pg_class AS tables
      ON tables.relnamespace = nsp.oid AND tables.relname = 'pg_authid'
    JOIN pg_catalog.pg_attribute AS attrs
      ON attrs.attrelid = tables.oid AND attrs.attname LIKE 'rol%'
    WHERE nsp.nspname = 'pg_catalog'
    ORDER BY 1
    """)

    @classmethod
    def update_supported_columns(cls, columns):
        cls.SUPPORTED_COLUMNS = [
            c for c in cls.SUPPORTED_COLUMNS
            if c in columns
        ]
        logger.debug(
            "Postgres server supports role options %s.",
            ", ".join(cls.supported_options()),
        )

    @classmethod
    def filter_super_columns(cls):
        cls.SUPPORTED_COLUMNS = [
            c for c in cls.SUPPORTED_COLUMNS
            if c not in cls.SUPERONLY_COLUMNS
        ]

    def __init__(self, *a, **kw):
        defaults = dict([(o, None) for c, (o, d) in self.COLUMNS.items()])
        super(RoleOptions, self).__init__(**defaults)
        init = dict(*a, **kw)
        self.update(init)

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self)

    def __str__(self):
        return ' '.join((
            ('NO' if value is False else '') + name
            for name, value in self.items()
            if name in self.supported_options()
        ))

    def update_from_row(self, row):
        self.update(dict(zip(self.supported_options(), row)))

    def update(self, other):
        spurious_options = set(other.keys()) - set(self.keys())
        if spurious_options:
            message = "Unknown options %s" % (', '.join(spurious_options),)
            raise ValueError(message)

        for k, their in other.items():
            my = self[k]
            if their is None:
                continue
            if my is None:
                self[k] = their
            elif my != their:
                raise ValueError("Two values defined for option %s." % k)

    def fill_with_defaults(self):
        defaults = dict([(o, d) for c, (o, d) in self.COLUMNS.items()])
        for k, v in self.items():
            if v is None:
                self[k] = defaults[k]


class RoleSet(set):
    def resolve_membership(self):
        index_ = self.reindex()
        for role in self:
            # Synchronize role.parents -> parent.members
            for parent_name in role.parents[:]:
                try:
                    parent = index_[parent_name]
                except KeyError:
                    raise ValueError('Unknown parent role %s' % parent_name)
                if role.name in parent.members:
                    continue
                parent.members.append(role.name)

            # Synchronize role.members -> member.parents
            for member_name in role.members[:]:
                try:
                    member = index_[member_name]
                except KeyError:
                    raise ValueError('Unknown member role %s' % member_name)
                if role.name in member.parents:
                    continue
                member.parents.append(role.name)

    def reindex(self):
        return dict([(role.name, role) for role in self])

    def flatten(self):
        # Generates the flatten tree of roles, children first.

        index = self.reindex()
        seen = set()

        def walk(name):
            if name in seen:
                return
            try:
                role = index[name]
            except KeyError:
                # We are trying to walk a member out of set. This is the case
                # where a role is missing but not one of its member.
                return

            for member in role.members:
                for i in walk(member):
                    yield i
            yield name
            seen.add(name)

        for name in sorted(index.keys()):
            for i in walk(name):
                yield index[i]

    def union(self, other):
        return self.__class__(self | other)

    def diff(
            self, other=None, available=None, fallback_owner=None,
            databases=None, me=None):
        # Yield query so that self match other. It's kind of a three-way diff
        # since we reuse `available` roles instead of recreating roles.

        available = available or RoleSet()
        # Available is a superset of self. Use the same index for self.
        index = available.reindex()
        other = other or RoleSet()

        # First create/rename missing roles
        missing = RoleSet(other - available)
        missing_index = missing.reindex()

        # newname -> oldrole
        renames = dict()

        # Search renames from upper/lower case to mixed case.
        for newrole in missing:
            loldrole = index.get(newrole.lname)
            uoldrole = index.get(newrole.uname)
            if loldrole and uoldrole:
                logger.debug(
                    "Can't choose renaming %s from %s or %s. Creating.",
                    newrole.name, loldrole.name, uoldrole.name)
                continue
            oldrole = loldrole or uoldrole
            if not oldrole:
                continue

            if oldrole in other:
                logger.debug(
                    "Wants both existing %s and new %s. Creating",
                    oldrole.name, newrole.name)
                continue
            renames[newrole.name] = oldrole

        # Search renames from mixed case to upper/lower case.
        for oldrole in available:
            lnewrole = missing_index.get(oldrole.lname)
            unewrole = missing_index.get(oldrole.uname)
            if lnewrole and unewrole:
                logger.debug(
                    "Can't choose renaming %s to %s or %s. Dropping.",
                    oldrole.name, lnewrole.name, unewrole.name)
                continue
            newrole = lnewrole or unewrole
            if not newrole:
                continue
            if oldrole in other:
                logger.debug(
                    "Wants both existing %s and new %s. Creating.",
                    oldrole.name, newrole.name)
                continue
            renames[newrole.name] = oldrole

        # Index renames by oldname
        # oldname -> newrole
        renamed = dict([
            (oldrole.name, missing_index[newname])
            for newname, oldrole in renames.items()
        ])

        # Create missing first, in order.
        for role in missing.flatten():
            if role.name in renames:
                continue

            # Create role using old case member name. Rename will be applied
            # just after.
            role.rename_members(renames)

            for qry in role.create():
                yield qry

        # Apply renames.
        for newname, oldrole in renames.items():
            newrole = missing_index[newname]
            for qry in oldrole.rename(newrole):
                yield qry
            # Update role inspection result to match rename.
            available.remove(oldrole)
            managed = oldrole in self
            if managed:
                self.remove(oldrole)
            oldrole.name = newrole.name
            available.add(oldrole)
            if managed:
                self.add(oldrole)

        index = available.reindex()

        # Now update kept roles options and memberships, including renamed.
        kept = available & other
        other_index = other.reindex()
        for role in kept:
            mine = index[role.name]
            # Rename back member to new role name, keeping objects synchronized
            # with Postgres instance.
            mine.rename_members(renamed)
            its = other_index[role.name]
            if role not in self:
                logger.warning(
                    "Role %s already exists in cluster. Reusing.", role.name)
            for qry in mine.alter(its):
                yield qry

        # Don't forget to trash all spurious managed roles!
        spurious = RoleSet(self - other - set(['public']))
        # reassign databases to fallback_owner
        for database in databases or []:
            if database.owner in spurious:
                for query in database.reassign(fallback_owner):
                    yield query
                # Update representation for the following queries.
                database.owner = fallback_owner

        for role in reversed(list(spurious.flatten())):
            for qry in role.drop(databases or [], me):
                yield qry


class RoleRule(object):
    def __init__(self, names, parents=None, members=None, options=None,
                 comment=None):
        self.comment = FormatList.factory([
            comment if comment else 'Managed by ldap2pg',
        ])
        self.members = FormatList.factory(members or [])
        self.names = FormatList.factory(names or [])
        self.options = options or {}
        self.parents = FormatList.factory(parents or [])
        self.all_fields = collect_fields(
            self.comment, self.members, self.names, self.parents,
        )

    def __eq__(self, other):
        return hasattr(other, 'as_dict') and self.as_dict() == other.as_dict()

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.names)

    @property
    def is_dynamic(self):
        return 0 != len(self.all_fields)

    @property
    def attributes_map(self):
        map_ = AttributesMap()
        for lst in self.comment, self.members, self.names, self.parents:
            map_.update(lst.attributes_map)
        return map_

    def copy(self, **kw):
        kw = dict(self.as_dict(), **kw)
        return self.__class__(**kw)

    def generate(self, vars_):
        names = self.names.expand(vars_)
        comments = comment_repeater(self.comment.expand(vars_))
        members = list(self.members.expand(vars_))
        parents = list(self.parents.expand(vars_))

        i = None
        for (i, name), (comment, repeated) in zip(enumerate(names), comments):
            yield Role(
                name=name,
                members=members[:],
                options=self.options,
                parents=parents[:],
                comment=comment,
            )

        # Check comment inconsistency, for generated comments.
        if i is None or repeated:
            return

        try:
            next(comments)
        except CommentError:  # All comments consumed.
            pass
        else:
            raise CommentError("We have more comments than names!")

    def as_dict(self):
        dict_ = {
            'comment': self.comment.formats[0] if self.comment else None,
            'options': self.options,
        }
        for k in "names", "members", "parents":
            dict_[k] = getattr(self, k).formats
        return dict_


class CommentError(Exception):
    pass


def comment_repeater(comments):
    # This generator handle the policy on comment.
    #
    # There is two cases where comment format yields a single value : static
    # comment and comment from a single LDAP value (e.g. cn). To handle this,
    # the generator repeats a single value forever.
    #
    # There is two cases that leads to inconsistent role generation: no comment
    # at all, or comment exhausted. This generator raises NoMoreComment
    # exception for this.
    #
    # A third case exists: there is more comments than role names. To handle
    # this, the generator yields two values: new comment and a boolean whether
    # comment is repeated.

    repeated = True

    try:
        value = next(comments)
    except StopIteration:
        raise CommentError("Can't generate a comment.")
    next_value = None

    while True:
        try:
            next_value = next(comments)
            repeated = False
        except StopIteration:
            if repeated:
                next_value = value
            else:
                break
        yield value, repeated
        value = next_value

    yield value, repeated

    raise CommentError("Can't generate more comment.")
