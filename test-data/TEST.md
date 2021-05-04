API zum Testen von CSW Links:
=============================
## New Data (from Tania Humar)
https://geocat-int.dev.bgdi.ch/geonetwork/srv/ger/csw-opendata-testgroup?service=CSW&version=2.0.2&request=GetRecords

https://geocat-int.dev.bgdi.ch/geonetwork/srv/ger/csw-opendata-testgroup?service=CSW&version=2.0.2&request=GetRecordById&id=3143e92b-51fa-40ab-bcc0-fa389807e879&elementsetname=full&outputSchema=http://www.isotc211.org/2005/gmd

## Neue Übergaben: 

Folgende Übergaben sind im Besipielsatz `test-record.xml` enthalten

### Nutzungsrechte

Ticket bei geocat: https://jira.swisstopo.ch/browse/GEOCATOD-20

```xml
    <gmd:resourceConstraints>
        <gmd:MD_LegalConstraints>
            <gmd:otherConstraints xsi:type="gmd:PT_FreeText_PropertyType">
                <gmx:Anchor>Opendata BY: Freie Nutzung. Quellenangabe ist Pflicht.</gmx:Anchor>
                <gmd:PT_FreeText>
                    <gmd:textGroup>
                        <gmd:LocalisedCharacterString locale="#DE">Opendata BY: Freie Nutzung. Quellenangabe
                            ist Pflicht.
                        </gmd:LocalisedCharacterString>
                    </gmd:textGroup>
                    <gmd:textGroup>
                        <gmd:LocalisedCharacterString locale="#FR">Opendata BY: Utilisation libre.
                            Obligation d’indiquer la source.
                        </gmd:LocalisedCharacterString>
                    </gmd:textGroup>
                    <gmd:textGroup>
                        <gmd:LocalisedCharacterString locale="#IT">Opendata BY: Libero utilizzo. Indicazione
                            della fonte obbligatoria. Utilizzo a fini commerciali ammesso soltanto previo
                            consenso del titolare dei dati
                        </gmd:LocalisedCharacterString>
                    </gmd:textGroup>
                    <gmd:textGroup>
                        <gmd:LocalisedCharacterString locale="#EN">Opendata BY: Open use. Must provide the
                            source.
                        </gmd:LocalisedCharacterString>
                    </gmd:textGroup>
                </gmd:PT_FreeText>
            </gmd:otherConstraints>
        </gmd:MD_LegalConstraints>
    </gmd:resourceConstraints>
```

### Map Preview

https://jira.swisstopo.ch/browse/GEOCATOD-15

### Rest-API

https://jira.swisstopo.ch/browse/GEOCATOD-26

### Mapping der Formate pro Ressource: GEOCATOD-3

https://jira.swisstopo.ch/browse/GEOCATOD-3