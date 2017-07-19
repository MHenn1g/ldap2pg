VERSION=$(shell python setup.py --version)

default:

release:
	python setup.py egg_info
	git commit ldap2pg/__init__.py -m "Version $(VERSION)"
	git tag $(VERSION)
	@echo
	@echo Now push with
	@echo
	@echo "    git push rw"
	@echo "    git push --tags rw"
	@echo
	@echo and upload with make upload

upload:
	git describe --exact-match --tags
	python3 setup.py sdist bdist_wheel upload -r pypi
