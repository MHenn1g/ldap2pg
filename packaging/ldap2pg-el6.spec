%define name ldap2pg
%define version 5.6
%define unmangled_version 5.6
%define release 1%{dist}

Summary: Manage PostgreSQL roles and privileges from YAML or LDAP
Name: %{name}
Version: %{version}
Release: %{release}
Source0: %{name}-%{unmangled_version}.tar.gz
License: PostgreSQL
Group: Development/Libraries
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-buildroot
Prefix: %{_prefix}
BuildArch: noarch
Vendor: Dalibo <contact@dalibo.com>
Requires: python-psycopg2 python-ldap PyYAML python-logutils python-argparse
Url: https://labs.dalibo.com/ldap2pg
BuildRequires: python2 python2-setuptools

%description
|ldap2pg|

| |CircleCI| |Codecov| |RTD| |PyPI| |Docker|

Swiss-army knife to synchronize Postgres roles and privileges from YAML or LDAP.

.. _documentation: https://ldap2pg.readthedocs.io/en/latest/
.. _license:       https://opensource.org/licenses/postgresql
.. _contributors:  https://github.com/dalibo/ldap2pg/blob/master/CONTRIBUTING.md#contributors


Features
========

- Creates, alters and drops PostgreSQL roles from LDAP searches.
- Creates static roles from YAML to complete LDAP entries.
- Manages role members (alias *groups*).
- Grants or revokes privileges statically or from LDAP entries.
- Dry run.
- Logs LDAP searches as ``ldapsearch`` commands.
- Logs **every** SQL query.
- Reads settings from an expressive YAML config file.

Here is a sample configuration and execution:

::

    $ cat ldap2pg.yml
    - role:
        name: ldap_roles
        options: NOLOGIN
    - ldapsearch:
        base: ou=people,dc=ldap,dc=ldap2pg,dc=docker
        filter: "(objectClass=organizationalPerson)"
      role:
        name: '{cn}'
        options: LOGIN
        parent: ldap_roles
    $ ldap2pg --real
    Starting ldap2pg 5.3.
    Using .../ldap2pg.yml.
    Running in real mode.
    Inspecting roles in Postgres cluster...
    Querying LDAP ou=people,dc=ldap,dc=lda... (objectClass...
    Create domitille.
    Add missing ldap_roles members.
    Delete spurious ldap_roles members.
    Update options of albert.
    Reassign oscar objects and purge ACL on postgres.
    Reassign oscar objects and purge ACL on template1.
    Drop oscar.
    Synchronization complete.
    $


See versionned `ldap2pg.yml
<https://github.com/dalibo/ldap2pg/blob/master/ldap2pg.yml>`_ and documentation_
for further options.


Installation
============

Install it from PyPI tarball::

    pip install ldap2pg psycopg2-binary

More details can be found in documentation_.


``ldap2pg`` is licensed under PostgreSQL license_. ``ldap2pg`` is available with
the help of wonderful people, jump to contributors_ list to see them.

``ldap2pg`` is reported to work with `OpenLDAP`_, `FreeIPA`_, Oracle Internet
Directory and Microsoft Active Directory.

.. _OpenLDAP: https://www.openldap.org/
.. _FreeIPA: https://www.freeipa.org/


Support
=======

If you need support and you didn't found it in documentation_, just drop a
question in a `GitHub issue <https://github.com/dalibo/ldap2pg/issues/new>`_!
French accepted. Don't miss the `cookbook
<https://ldap2pg.readthedocs.io/en/latest/cookbook/>`_. You're welcome!


.. |Codecov| image:: https://codecov.io/gh/dalibo/ldap2pg/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/dalibo/ldap2pg
   :alt: Code coverage report

.. |CircleCI| image:: https://circleci.com/gh/dalibo/ldap2pg.svg?style=shield
   :target: https://circleci.com/gh/dalibo/ldap2pg
   :alt: Continuous Integration report

.. |Docker| image:: https://img.shields.io/docker/automated/dalibo/ldap2pg.svg
   :target: https://hub.docker.com/r/dalibo/ldap2pg
   :alt: Docker Image Available

.. |ldap2pg| image:: https://github.com/dalibo/ldap2pg/raw/master/docs/img/logo-phrase.png
   :target: https://labs.dalibo.com/ldap2pg
   :alt: ldap2pg: PostgreSQL role and privileges management

.. |PyPI| image:: https://img.shields.io/pypi/v/ldap2pg.svg
   :target: https://pypi.python.org/pypi/ldap2pg
   :alt: Version on PyPI

.. |RTD| image:: https://readthedocs.org/projects/ldap2pg/badge/?version=latest
   :target: https://ldap2pg.readthedocs.io/en/latest/?badge=latest
   :alt: Documentation


%prep
%setup -n %{name}-%{unmangled_version} -n %{name}-%{unmangled_version}

%build
/usr/bin/python2 setup.py build

%install
/usr/bin/python2 setup.py install --single-version-externally-managed -O1 --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES

%clean
rm -rf $RPM_BUILD_ROOT

%files -f INSTALLED_FILES
%defattr(-,root,root)
