import sys
from pprint import pprint
import ckan.lib.cli
import ckanext.geocat.metadata as md


class GeocatCommand(ckan.lib.cli.CkanCommand):
    '''Command to query geocat

    Usage::

            paster geocat search birds
            paster geocat cql "csw:AnyText like '%birds%'"

    '''
    summary = __doc__.split('\n')[0]
    usage = __doc__

    def command(self):
        options = {
            'search': self.searchCmd,
            'cql': self.cqlCmd,
            'dataset': self.datasetCmd,
            'help': self.helpCmd,
        }

        try:
            cmd = self.args[0]
            options[cmd](*self.args[1:])
        except KeyError:
            self.helpCmd()

    def helpCmd(self):
        print self.__doc__

    def cqlCmd(self, query=None):
        if (query is None):
            print "Argument 'query' must be set"
            self.helpCmd()
            sys.exit(1)
        csw = md.CswHelper('http://www.geocat.ch/geonetwork/srv/eng/csw')
        for xml, value in csw.get_by_search(cql=query):
            print xml

    def datasetCmd(self, query=None):
        geocat = md.GeocatDcatDatasetMetadata()
        for metadata in geocat.get_metadata():
            pprint(metadata)

    def searchCmd(self, query=None):
        if (query is None):
            print "Argument 'query' must be set"
            self.helpCmd()
            sys.exit(1)
        csw = md.CswHelper('http://www.geocat.ch/geonetwork/srv/eng/csw')
        for xml, value in csw.get_by_search(query):
            print xml
