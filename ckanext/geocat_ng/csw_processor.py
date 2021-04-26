# -*- coding: utf-8 -*-

from datetime import datetime
import time
from collections import defaultdict
from urlparse import urlparse
from owslib.csw import CatalogueServiceWeb
from owslib.fes import PropertyIsEqualTo
from ckanext.geocat_ng import csw_mapping

import logging
log = logging.getLogger(__name__)


class GeocatCatalogueServiceWeb(object):
    def __init__(self, url):
        self.csw = CatalogueServiceWeb(url)
        self.schema = csw_mapping.namespaces['che']

    def get_geocat_id_from_csw(self):
        harvest_query = PropertyIsEqualTo('keyword', 'opendata.swiss')
        nextrecord = 0
        record_ids = []
        while nextrecord is not None:
            self.csw.getrecords2(constraints=[harvest_query], maxrecords=50, startposition=nextrecord)
            if (self.csw.response is None or self.csw.results['matches'] == 0):
                raise DatasetNotFoundError("No dataset found" % cql)
            if self.csw.results['returned'] > 0:
                if self.csw.results['nextrecord'] > 0:
                    nextrecord = self.csw.results['nextrecord']
                else:
                    nextrecord = None
                for id in self.csw.records.keys():
                    record_ids.append(id)
        log.error(record_ids)
        return record_ids

    def get_record_by_id(self, geocat_id):
        # self.schema = 'http://www.geocat.ch/2008/che'
        self.csw.getrecordbyid(id=[geocat_id], outputschema=self.schema)
        csw_record_as_string = self.csw.response
        if csw_record_as_string:
            dataset_dict = csw_mapping.process_geodata(csw_record_as_string)
            log.error(dataset_dict)
            return dataset_dict


class DatasetNotFoundError(Exception):
    pass
