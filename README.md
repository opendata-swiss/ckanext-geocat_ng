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


## CLI Commands

This extension provides a number of CLI commands to query/debug the results of the CSW server.


### `search`

To run an arbitrary query against the defined CSW server use the `search` command:

```
paster geocat search birds
```

This command takes an optional second parameter to specifiy the CSW url (defaults to `http://www.geocat.ch/geonetwork/srv/eng/csw`)

### `cql`

To run an arbitrary CQL query against the defined CSW server use the `cql` command:

```
paster geocat cql "csw:AnyText like '%birds%'"
paster geocat cql "keyword = 'opendata.swiss'" https://www.geocat.ch/geonetwork/srv/eng/csw-ZH
```

This command takes an optional second parameter to specifiy the CSW url (defaults to `http://www.geocat.ch/geonetwork/srv/eng/csw`)

### `list`

To list all IDs from the defined CSW server use the `list` command:

```
paster geocat list
paster geocat list "keyword = 'opendata.swiss'" 
paster geocat list "keyword = 'opendata.swiss'" https://www.geocat.ch/geonetwork/srv/eng/csw-ZH/
```

The first parameter is an arbitrary CQL query, if you omit it, the default query is used (`keyword = 'opendata.swiss'`).

This command takes an optional second parameter to specifiy the CSW url (defaults to `http://www.geocat.ch/geonetwork/srv/eng/csw`)

### `dataset`

To get a specific record (by ID), use the `dataset` command.
Use the `list` command above to get an ID:

```
paster geocat dataset "1eac72b1-068d-4272-b011-d0010cc4bf676"
paster geocat dataset "8ae7eeb1-04d4-4c78-93e1-4225412db6a4" https://www.geocat.ch/geonetwork/srv/eng/csw-ZH/
```

This command takes an optional second parameter to specifiy the CSW url (defaults to `http://www.geocat.ch/geonetwork/srv/eng/csw`)

The output shows the returned XML from the CSW and the parsed dataset and distribution dictionaries.

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
