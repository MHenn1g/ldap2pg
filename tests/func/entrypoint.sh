#!/bin/bash -eux

teardown() {
	# If not on CI, wait for user interrupt on exit
	if [ -z "${CI-}" -a "$?" -gt 0 -a $$ = 1 ] ; then
		sleep infinity
	fi
}

trap teardown EXIT TERM

top_srcdir=$(readlink -m $0/../../..)
cd $top_srcdir
test -f setup.py

export LC_ALL=en_US.utf8

# Choose target Python version. Matches packaging/rpm/build_rpm.sh.
rpmdist=$(rpm --eval '%dist')
case "$rpmdist" in
	*.el7|*.el8)
		python=python3.6
		pip=pip3.6
		;;
	*.el6)
		python=python2
		pip=pip2
		;;
esac
fullname=$($python setup.py --fullname)

# Search for the proper RPM package.
rpms=(dist/${fullname}-*${rpmdist}.noarch.rpm)
rpm=${rpms[0]}
test -f "$rpm"

# Clean and install package.
if rpm --query --queryformat= ldap2pg ; then
	yum -q -y remove ldap2pg
fi

yum -q -y install "$rpm"
ldap2pg --version

# Check Postgres and LDAP connectivity
psql -tc "SELECT version();"
# ldap-utils on CentOS does not read properly current ldaprc. Linking it in ~
# workaround this.
ln -fsv "${PWD}/ldaprc" ~/ldaprc
ldapwhoami -x -d 1 -w "${LDAPPASSWORD}"

"$pip" --version
if "$pip" --version |& grep -Fiq "python 2.6" ; then
	pip26-install https://files.pythonhosted.org/packages/53/67/9620edf7803ab867b175e4fd23c7b8bd8eba11cb761514dcd2e726ef07da/py-1.4.34-py2.py3-none-any.whl
	pip26-install https://files.pythonhosted.org/packages/fd/3e/d326a05d083481746a769fc051ae8d25f574ef140ad4fe7f809a2b63c0f0/pytest-3.1.3-py2.py3-none-any.whl
	pip26-install https://files.pythonhosted.org/packages/86/84/6bd1384196a6871a9108157ec934a1e1ee0078582cd208b43352566a86dc/pytest_catchlog-1.2.2-py2.py3-none-any.whl
	pip26-install https://files.pythonhosted.org/packages/4a/22/17b22ef5b049f12080f5815c41bf94de3c229217609e469001a8f80c1b3d/sh-1.12.14-py2.py3-none-any.whl
else
	"$pip" install --prefix=/usr/local --requirement tests/func/requirements.txt
fi

if [ -n "${CI+x}" ] ; then
    # We can't modify config with ldapmodify. This prevent us to setup SASL in
    # CircleCI.
    ldapmodify -xw "${LDAPPASSWORD}" -f ./fixtures/openldap-data.ldif
fi

"$python" -c "import sys; print(sys.stdout)"
"$python" -m pytest -x tests/func/
