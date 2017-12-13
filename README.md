[![Build Status](https://travis-ci.org/opendata-swiss/ckanext-geocat.svg?branch=master)](https://travis-ci.org/opendata-swiss/ckanext-geocat)

ckanext-geocat
=============

This extension harvests data from the Swiss CSW service [geocat.ch](http://geocat.ch) to the Swiss open data portal [opendata.swiss](https://opendata.swiss).
The source format is ISO-19139_che (Swiss version of ISO-19139), the target format is DCAT-AP Switzerland.


## Requirements

CKAN >= 2.4

## Installation

To install ckanext-geocat:

1. Activate your CKAN virtual environment, for example:

     . /usr/lib/ckan/default/bin/activate

2. Install the ckanext-geocat Python package into your virtual environment:

     pip install ckanext-geocat

3. Add ``geocat`` to the ``ckan.plugins`` setting in your CKAN
   config file (by default the config file is located at
   ``/etc/ckan/default/production.ini``).

4. Restart CKAN. For example if you've deployed CKAN with Apache on Ubuntu:

     sudo service apache2 reload


## Config Settings

To configure the harvester you have several harvester config options (in the harvester config JSON):

* `rights`: The terms of use to be associated with all harvested datasets (default: `NonCommercialNotAllowed-CommercialNotAllowed-ReferenceRequired`)
* `cql`: The CQL query to be used when requesting the CSW service (default: `keyword = 'opendata.swiss'`)
* `user`: The user to be used when importing the datasets (default: `harvest`)
* `organization`: The organization to be associated to all harvested datasets (default: the organization, which owns the harvest source)


## Development Installation

To install ckanext-geocat for development, activate your CKAN virtualenv and
do::

    git clone https://github.com/ogdch/ckanext-geocat.git
    cd ckanext-geocat
    python setup.py develop
    pip install -r dev-requirements.txt
    pip install -r requirements.txt


# Running the Checks

To run the code checks use:

    flake8

# Run the tests

To run the tests use the following command

    nosetests
