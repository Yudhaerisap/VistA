""" This module is going to parse ICR in JSON format and convert to html web page
"""
import json
import argparse
import os.path
import cgi
import logging
import pprint

from LogManager import logger, initConsoleLogging
from ICRSchema import ICR_FILE_KEYWORDS_LIST, SUBFILE_FIELDS
from ICRSchema import isSubFile, isWordProcessingField
from WebPageGenerator import getPackageHtmlFileName, getGlobalHtmlFileNameByName
from WebPageGenerator import getRoutineHtmlFileName
from WebPageGenerator import pkgMap
from DataTableHtml import outputDataTableHeader, outputDataTableFooter
from DataTableHtml import writeTableListInfo, outputDataListTableHeader
from DataTableHtml import outputLargeDataListTableHeader, outputDataRecordTableHeader
from DataTableHtml import outputFileEntryTableList, safeElementId
from InitCrossReferenceGenerator import createInitialCrossRefGenArgParser
from InitCrossReferenceGenerator import parseCrossReferenceGeneratorArgs
from FileManGlobalDataParser import generateSingleFileFieldToIenMappingBySchema

dox_url = "http://code.osehra.org/dox/"



def normalizeName(name):
    return name.replace('/', ' ').replace('\'','').replace(',','').replace('.','').replace('&', 'and')

def useAjaxDataTable(len):
    return len > 4000 # if has more than 4000 entries, use ajax approach

pgkUpperCaseNameDict = dict()
rpcNameToIenMapping = dict()
RPC_FILE_NO = '8994'
RPC_NAME_FIELD_NO = '.01'

def addToPackageMap(icrEntry, pkgName):
    if 'CUSTODIAL PACKAGE' in icrEntry:
        icrPkg = icrEntry['CUSTODIAL PACKAGE']
        if icrPkg not in pkgMap:
            pkgMap[icrPkg] = pkgName
            logger.debug('[%s] ==> [%s]', icrPkg, pkgName)
        elif pkgMap[icrPkg] != pkgName:
            logger.debug('[%s] mapped to [%s] and [%s]', icrPkg, pkgMap[icrPkg], pkgName)

""" Util function to generate link for the fie """
def getICRIndividualHtmlFileLinkByIen(value, icrEntry, **kargs):
    ien = icrEntry['NUMBER']
    ienDescription = ''
    if "GENERAL DESCRIPTION" in icrEntry:
      for line in icrEntry["GENERAL DESCRIPTION"]:
        if not line:  # Empty string
          ienDescription += '\n'
        else:
          ienDescription += ' ' + cgi.escape(line).replace('"', r"&quot;").replace("'", r"&quot;")
    return '<a title=\"%s\" href=\"%s\">%s</a>' % (ienDescription,'ICR-' + ien + '.html', value)

def getGeneralDescription(value, icrEntry, **kargs):
    description = ""
    if "GENERAL DESCRIPTION" in icrEntry:
      for line in icrEntry["GENERAL DESCRIPTION"]:
        if not line:  # Empty string
          description += '\n'
        else:
          description += '<br>' + cgi.escape(line).replace('"', r"&quot;").replace("'", r"&quot;")
    return description

def getPackageHRefLink(pkgName, icrEntry, **kargs):
    if pkgName in pkgMap:
        pkgLink = getPackageHtmlFileName(pkgMap[pkgName])
        return '<a href=\"%s%s\">%s</a>' % (dox_url, pkgLink , pkgName)
    crossRef = None
    if 'crossRef' in kargs:
        crossRef = kargs['crossRef']
    if crossRef:
        if len(pgkUpperCaseNameDict) == 0 :
            for name in crossRef.getAllPackages().iterkeys():
                pgkUpperCaseNameDict[name.upper()] = name
        upperName = normalizeName(pkgName).upper()
        if upperName in pgkUpperCaseNameDict:
            addToPackageMap(icrEntry, pgkUpperCaseNameDict[upperName])
            return '<a href=\"%s%s\">%s</a>' % (dox_url, getPackageHtmlFileName(pgkUpperCaseNameDict[upperName]) , pkgName)
        pkg = crossRef.getPackageByName(pkgName)
        if not pkg:
            pkgRename = normalizeName(pkgName).title()
            # logger.warn('[%s] renamed as [%s]', pkgName, pkgRename)
            pkg = crossRef.getPackageByName(pkgRename)
        if not pkg:
            pkgRename = normalizeName(pkgName)
            pkg = crossRef.getPackageByName(pkgRename)
        if pkg:
            addToPackageMap(icrEntry, pkg.getName())
            pkgLink = getPackageHtmlFileName(pkg.getName())
            return '<a href=\"%s%s\">%s</a>' % (dox_url, pkgLink , pkgName)
        else:
            logger.warn('Can not find mapping for package: [%s]', pkgName)
    return pkgName

def getFileManFileHRefLink(fileNo, icrEntry, **kargs):
    crossRef = None
    if 'crossRef' in kargs:
        crossRef = kargs['crossRef']
    if crossRef:
        fileInfo = crossRef.getGlobalByFileNo(fileNo)
        if fileInfo:
            linkName = getGlobalHtmlFileNameByName(fileInfo.getName())
            logger.debug('link is [%s]', linkName)
            # addToPackageMap(icrEntry, fileInfo.getPackage().getName())
            return '<a href=\"%s%s\">%s</a>' % (dox_url, linkName, fileNo)
        else:
            logger.debug('Can not find file: [%s]', fileNo)
    return fileNo

def getRoutineHRefLink(rtnName, icrEntry, **kargs):
    crossRef = None
    if 'crossRef' in kargs:
        crossRef = kargs['crossRef']
    if crossRef:
        routine = crossRef.getRoutineByName(rtnName)
        if routine:
            logger.debug('Routine Name is %s, package: %s', routine.getName(), routine.getPackage())
            # addToPackageMap(icrEntry, routine.getPackage().getName())
            return '<a href=\"%s%s\">%s</a>' % (dox_url, getRoutineHtmlFileName(routine.getName()), rtnName)
        else:
            logger.debug('Can not find routine [%s]', rtnName)
            logger.debug('After Categorization: routine: [%s], info: [%s]', rtnName, crossRef.categorizeRoutineByNamespace(rtnName))
    return rtnName

def getRPCHRefLink(rpcName, icrEntry, **kargs):
    if rpcName in rpcNameToIenMapping:
        rpcFilename = '%s-%s.html' % (RPC_FILE_NO, rpcNameToIenMapping[rpcName])
        return '<a href=\"%s\">%s</a>' % (rpcFilename, rpcName)
    return rpcName

""" A list of fields that are part of the summary page for each package or all """
summary_list_fields = [
    ('IA #', 'NUMBER', None),
    ('Name', None, getICRIndividualHtmlFileLinkByIen),
    ('Type', None, None),
    ('Custodial Package', None, getPackageHRefLink),
    # ('Custodial ISC', None),
    ('Date Created', None, None),
    ('DBIC Approval Status', None, None),
    ('Status', None, None),
    ('Usage', None, None),
    ('File #', 'FILE NUMBER', getFileManFileHRefLink),
    ('General Description', None, getGeneralDescription),
    # ('Global root', None, None),
    ('Remote Procedure', None, getRPCHRefLink),
    ('Routine', None, getRoutineHRefLink),
    ('Date Activated', None, None)
]

field_convert_map = {
    'FILE NUMBER': getFileManFileHRefLink,
    'GENERAL DESCRIPTION': getGeneralDescription,
    'ROUTINE': getRoutineHRefLink,
    'CUSTODIAL PACKAGE': getPackageHRefLink,
    'SUBSCRIBING PACKAGE': getPackageHRefLink,
    'REMOTE PROCEDURE': getRPCHRefLink
}

class ICRJsonToHtml(object):

    def __init__(self, crossRef, outDir):
        self._crossRef = crossRef
        self._outDir = outDir
    """
    This is the entry point to convert JSON to html web pages

    It will generate a total ICR summary page as well individual pages for each package.
    It will also generate the pages for each individual ICR details

    """
    def convertJsonToHtml(self, inputJsonFile, date):
        with open(inputJsonFile, 'r') as inputFile:
            inputJson = json.load(inputFile)
            self._generateICRSummaryPage(inputJson, date)

    """ Utility function to convert icrEntry to summary info """
    def _convertICREntryToSummaryInfo(self, icrEntry):
        summaryInfo = [""]*len(summary_list_fields)
        for idx, id in enumerate(summary_list_fields):
            if id[1] and id[1] in icrEntry:
                summaryInfo[idx] = icrEntry[id[1]]
            elif id[0].upper() in icrEntry:
                summaryInfo[idx] = icrEntry[id[0].upper()]
            if summaryInfo[idx] and id[2]:
                summaryInfo[idx] = id[2](summaryInfo[idx], icrEntry, crossRef=self._crossRef)
        return summaryInfo

    """ Summary page will contain summary information
    """
    def _generateICRSummaryPage(self, inputJson, date):
        pkgJson = {} # group by package
        allpgkJson = []
        for icrEntry in inputJson:
            self._generateICRIndividualPage(icrEntry, date)
            summaryInfo = self._convertICREntryToSummaryInfo(icrEntry)
            allpgkJson.append(summaryInfo)
            if 'CUSTODIAL PACKAGE' in icrEntry:
                pkgJson.setdefault(icrEntry['CUSTODIAL PACKAGE'],[]).append(summaryInfo)
        self._generateICRSummaryPageImpl(allpgkJson, 'ICR List', 'All', date, True)
        for pkgName, outJson in pkgJson.iteritems():
            self._generateICRSummaryPageImpl(outJson, 'ICR List', pkgName, date)
        logger.warn('Total # entry in pkgMap is [%s]', len(pkgMap))
        logger.warn('Total # entry in pkgJson is [%s]', len(pkgJson))
        pprint.pprint(set(pkgJson.keys()) - set(pkgMap.keys()))
        pprint.pprint(set(pgkUpperCaseNameDict.values()) - set(pkgMap.values()))
        # pprint.pprint(pkgMap)
        self._generatePkgDepSummaryPage(inputJson, date)

    def _generatePkgDepSummaryPage(self, inputJson, date):
        outDep = {}
        for icrItem in inputJson:
            curIaNum = icrItem['IA #']
            # ignore the non-active icrs
            if 'STATUS' not in icrItem or icrItem['STATUS'] != 'Active':
                continue
            if 'CUSTODIAL PACKAGE' in icrItem:
                curPkg = icrItem['CUSTODIAL PACKAGE']
                outDep.setdefault(curPkg,{})
                if 'SUBSCRIBING PACKAGE' in icrItem:
                    for subPkg in icrItem['SUBSCRIBING PACKAGE']:
                        if 'SUBSCRIBING PACKAGE' in subPkg:
                            subPkgName = subPkg['SUBSCRIBING PACKAGE']
                            if isinstance(subPkgName,list):
                              for subPkgNameEntry in subPkgName:
                                subDep = outDep.setdefault(subPkgNameEntry, {}).setdefault('dependencies',{})
                                subDep.setdefault(curPkg, []).append(curIaNum)
                                curDep = outDep.setdefault(curPkg, {}).setdefault('dependents', {})
                                curDep.setdefault(subPkgNameEntry, []).append(curIaNum)
                            else:
                              subDep = outDep.setdefault(subPkgName, {}).setdefault('dependencies',{})
                              subDep.setdefault(curPkg, []).append(curIaNum)
                              curDep = outDep.setdefault(curPkg, {}).setdefault('dependents', {})
                              curDep.setdefault(subPkgName, []).append(curIaNum)
        """ Convert outDep to html page """
        outDir = self._outDir
        outFilename = "%s/ICR-PackageDep.html" % outDir
        with open(outFilename, 'w+') as output:
            output.write("<html>\n")
            tName = safeElementId("%s-%s" % ('ICR', 'PackageDep'))
            outputDataListTableHeader(output, tName)
            output.write("<body id=\"dt_example\">")
            output.write("""<div id="container" style="width:80%">""")
            outputDataTableHeader(output, ['Package Name', 'Dependencies Information'], tName)
            """ table body """
            output.write("<tbody>\n")
            """ Now convert the ICR Data to Table data """
            for pkgName in sorted(outDep.iterkeys()):
                output.write("<tr>\n")
                output.write("<td>%s</td>\n" % getPackageHRefLink(pkgName, {'CUSTODIAL PACKAGE': pkgName}, crossRef=self._crossRef))
                """ Convert the dependencies and dependent information """
                output.write("<td>\n")
                output.write ("<ol>\n")
                for pkgDepType in sorted(outDep[pkgName].iterkeys()):
                    output.write ("<li>\n")
                    output.write ("<dt>%s:</dt>\n" % pkgDepType.upper())
                    depPkgInfo = outDep[pkgName][pkgDepType]
                    for depPkgName in sorted(depPkgInfo.iterkeys()):
                        outputInfo = getPackageHRefLink(depPkgName, {'CUSTODIAl PACKAGE': depPkgName}, crossRef=self._crossRef)
                        outputInfo += ': &nbsp;&nbsp Total # of ICRs %s : [' % len(depPkgInfo[depPkgName])
                        for icrNo in depPkgInfo[depPkgName]:
                            outputInfo += getICRIndividualHtmlFileLinkByIen(icrNo, {'NUMBER': icrNo}, crossRef=self._crossRef) + '&nbsp;&nbsp'
                        outputInfo += ']'
                        output.write ("<dt>%s:</dt>\n" % outputInfo)
                    output.write ("</li>\n")
                output.write ("</ol>\n")
                output.write("</td>\n")
                output.write ("</tr>\n")
            output.write("</tbody>\n")
            output.write("</table>\n")
            if date is not None:
                link = "http://foia-vista.osehra.org/VistA_Integration_Agreement/"
                output.write("<a href=\"%s\">Generated from %s IA Listing Descriptions</a>" % (link, date))
            output.write("</div>\n")
            output.write("</div>\n")
            output.write ("</body></html>\n")

    def _generateICRSummaryPageImpl(self, inputJson, listName, pkgName, date, isForAll=False):
        outDir = self._outDir
        listName = listName.strip()
        pkgName = pkgName.strip()
        pkgHtmlName = pkgName
        outFilename = "%s/%s-%s.html" % (outDir, pkgName, listName)
        if not isForAll:
            if pkgName in pkgMap:
                pkgName = pkgMap[pkgName]
            pkgHtmlName = pkgName + '-ICR.html'
            outFilename = "%s/%s" % (outDir, pkgHtmlName)
        with open(outFilename, 'w+') as output:
            output.write("<html>\n")
            tName = "%s-%s" % (listName.replace(' ', '_'), pkgName.replace(' ', '_'))
            useAjax = useAjaxDataTable(len(inputJson))
            columnNames = [x[0] for x in summary_list_fields]
            searchColumns = ['IA #', 'Name', 'Custodial Package',
                             'Date Created', 'File #', 'Remote Procedure',
                             'Routine', 'Date Activated', 'General Description']
            hideColumns = ['General Description']
            if useAjax:
                ajaxSrc = '%s_array.txt' % pkgName
                outputLargeDataListTableHeader(output, ajaxSrc, tName,
                                               columnNames, searchColumns,
                                               hideColumns)
            else:
                outputDataListTableHeader(output, tName, columnNames,
                                          searchColumns, hideColumns)
            output.write("<body id=\"dt_example\">")
            output.write("""<div id="container" style="width:80%">""")

            if isForAll:
                output.write("<h1>%s %s</h1>" % (pkgName, listName))
            else:
                output.write("<h2 align=\"right\"><a href=\"./All-%s.html\">"
                             "All %s</a></h2>" % (listName, listName))
                output.write("<h1>Package: %s %s</h1>" % (pkgName, listName))
            # pkgLinkName = getPackageHRefLink(pkgName)
            outputDataTableHeader(output, columnNames, tName)
            outputDataTableFooter(output, columnNames, tName)
            """ table body """
            output.write("<tbody>\n")
            if not useAjax:
                """ Now convert the ICR Data to Table data """
                for icrSummary in inputJson:
                    output.write("<tr>\n")
                    for item in icrSummary:
                        #output.write("<td class=\"ellipsis\">%s</td>\n" % item)
                        output.write("<td>%s</td>\n" % item)
                    output.write("</tr>\n")
            else:
                logging.info("Ajax source file: %s" % ajaxSrc)
                """ Write out the data file in JSON format """
                outJson = {"aaData": []}
                with open(os.path.join(outDir, ajaxSrc), 'w') as ajaxOut:
                    outArray =  outJson["aaData"]
                    for icrSummary in inputJson:
                        outArray.append(icrSummary)
                    json.dump(outJson, ajaxOut)
            output.write("</tbody>\n")
            output.write("</table>\n")
            if date is not None:
                link = "http://foia-vista.osehra.org/VistA_Integration_Agreement/"
                output.write("<a href=\"%s\">Generated from %s IA Listing Descriptions</a>" % (link, date))
            output.write("</div>\n")
            output.write("</div>\n")
            output.write ("</body></html>\n")

    """ This is to generate a web page for each individual ICR entry """
    def _generateICRIndividualPage(self, icrJson, date):
        ien = icrJson['NUMBER']
        outIcrFile = os.path.join(self._outDir, 'ICR-' + ien + '.html')
        tName = safeElementId("%s-%s" % ('ICR', ien))
        with open(outIcrFile, 'w') as output:
            output.write ("<html>")
            outputDataRecordTableHeader(output, tName)
            output.write("<body id=\"dt_example\">")
            output.write("""<div id="container" style="width:80%">""")
            output.write ("<h1>%s (%s) &nbsp;&nbsp;  %s (%s)</h1>\n" % (icrJson['NAME'], ien,
                                                              'ICR',
                                                              ien))
            outputFileEntryTableList(output, tName)
            """ table body """
            self._icrDataEntryToHtml(output, icrJson)
            output.write("</tbody>\n")
            output.write("</table>\n")
            if date is not None:
                link = "http://foia-vista.osehra.org/VistA_Integration_Agreement/"
                output.write("<a href=\"%s\">Generated from %s IA Listing Descriptions</a>" % (link, date))
            output.write("</div>\n")
            output.write("</div>\n")
            output.write ("</body></html>")

    def _icrDataEntryToHtml(self, output, icrJson):
        fieldList = ICR_FILE_KEYWORDS_LIST
        """ As we do not have a real schema to define the field order,
             we will have to guess the order here
        """
        for field in fieldList:
            if field in icrJson: # we have this field
                value = icrJson[field]
                if isSubFile(field):
                    output.write ("<tr>\n")
                    output.write("<td>%s</td>\n" % field)
                    output.write("<td>\n")
                    output.write ("<ol>\n")
                    self._icrSubFileToHtml(output, value, field)
                    output.write ("</ol>\n")
                    output.write("</td>\n")
                    output.write ("</tr>\n")
                    continue
                value = self._convertIndividualFieldValue(field, icrJson, value)
                output.write ("<tr>\n")
                output.write ("<td>%s</td>\n" % field)
                output.write ("<td>%s</td>\n" % value)
                output.write ("</tr>\n")

    def _icrSubFileToHtml(self, output, icrJson, subFile):
        logger.debug('subFile is %s', subFile)
        logger.debug('icrJson is %s', icrJson)
        fieldList = SUBFILE_FIELDS[subFile]
        if subFile not in fieldList:
            fieldList.append(subFile)
        for icrEntry in icrJson:
            output.write ("<li>\n")
            for field in fieldList:
                if field in icrEntry: # we have this field
                    value = icrEntry[field]
                    logger.debug('current field is %s', field)
                    if isSubFile(field) and field != subFile: # avoid recursive subfile for now
                        logger.debug('field is a subfile %s', field)
                        output.write ("<dl><dt>%s:</dt>\n" % field)
                        output.write ("<dd>\n")
                        output.write ("<ol>\n")
                        self._icrSubFileToHtml(output, value, field)
                        output.write ("</ol>\n")
                        output.write ("</dd></dl>\n")
                        continue
                    value = self._convertIndividualFieldValue(field, icrEntry, value)
                    output.write ("<dt>%s:  &nbsp;&nbsp;%s</dt>\n" % (field, value))
            output.write ("</li>\n")

    def _convertIndividualFieldValue(self, field, icrEntry, value):
        if isWordProcessingField(field):
            if type(value) is list:
                value = "\n".join(value)
            value = '<pre>\n' + cgi.escape(value) + '\n</pre>\n'
            return value
        if field in field_convert_map:
            if type(value) is list:
                logger.warn('field: [%s], value:[%s], icrEntry: [%s]', field, value, icrEntry)
                return value
            value = field_convert_map[field](value, icrEntry, crossRef=self._crossRef)
            return value
        return value
    """ This function will read all entries in RPC file file# 8994 and return a mapping
        of RPC Name => IEN.
    """


def createArgParser():
    initParser = createInitialCrossRefGenArgParser()
    parser = argparse.ArgumentParser(description='VistA ICR JSON to Html',
                                     parents=[initParser])
    parser.add_argument('icrJsonFile', help='path to the VistA ICR JSON file')
    parser.add_argument('outDir', help='path to the output web page directory')
    return parser

def createRemoteProcedureMapping(MRepositDir, crossRef):
    return generateSingleFileFieldToIenMappingBySchema(MRepositDir,
                                                       crossRef,
                                                       RPC_FILE_NO,
                                                       RPC_NAME_FIELD_NO)

def run(args):
    crossRef = parseCrossReferenceGeneratorArgs(args.MRepositDir,
                                                args.patchRepositDir)
    rpcNameToIenMapping = createRemoteProcedureMapping(args.MRepositDir, crossRef)
    icrJsonToHtml = ICRJsonToHtml(crossRef, args.outDir)
    if hasattr(args, 'date'):
        date = args.date
    else:
        date = None
    icrJsonToHtml.convertJsonToHtml(args.icrJsonFile, date)


if __name__ == '__main__':
    parser = createArgParser()
    result = parser.parse_args()
    initConsoleLogging()
    run(result)
