#!/usr/bin/env python3.6

"""This version relies on style attribute patterns"""


import os
import re
import sys
from io import BytesIO, StringIO
from argparse import ArgumentParser
from collections import defaultdict, namedtuple

import lxml.etree as ET
from unidecode import unidecode

xml_namespace = 'http://www.w3.org/XML/1998/namespace'

# source ids for editions
edition_ids = {
    '01': {'M': 'M', 'Sr': 'Sr', 'St': 'St', 'W': 'W', 'DJAK03': 'DJAK03'},
    '02': {'DJAK03': 'DJAK03', 'T1619': 'T1619'},
    '03': {'B': 'B', 'S': 'St', 'T': 'T', 'W': 'W', 'DJAK03': 'DJAK03'},
    '04': {'Nov': 'Nov', 'Sr':'Sr', 'St': 'St', 'DJAK03': 'DJAK03'},
    '05': {'Šk': 'Šk', 'RKP': 'RKP', 'T1663': 'T1663', 'T1631': 'T1631', 'DJAK03': 'DJAK03'},
    '06': {'DJAK03': 'DJAK03', 'St': 'St',},
    '07': {'Nov': 'Nov', 'Souček': 'Souček', 'T1624': 'T1624', 'DJAK03': 'DJAK03'},
    '08': {'A': 'T1663', 'L': 'T1633', 'V': 'W', 'DJAK03': 'DJAK03'},
    '09': {'DJAK03': 'DJAK03', 'T1632': 'T1632'},
    '10': {'DJAK03': 'DJAK03', 'T1650': 'T1650'}
}

default_edition_ids = {
    '01': {'DJAK03': 'St'},
    '02': {'DJAK03': 'T1619'},
    '03': {'DJAK03': 'B'},
    '04': {'DJAK03': 'St'},
    '05': {'DJAK03': 'DJAK03'},
    '06': {'DJAK03': 'St'},
    '07': {'DJAK03': 'T1624'},
    '08': {'DJAK03': 'T1663'},
    '09': {'DJAK03': 'T1632'},
    '10': {'DJAK03': 'T1650'}
}

labyrint_wits = {
    'a': ('#DJAK03', '#T1663'),
    'b': ('#DJAK03', '#RKP'),
    'c': ('#DJAK03', '#T1631')
}

# edition for edition page breaks is hardcoded here
pb_pe_ed = 'DJAK03'
# edition for original page breaks
pb_po_ed = ''
# id template for anchor
anchor_id_template = ''
# from template for app
app_id_template = ''

PLAIN_STYLE = ['plain', 'normal']
ENCLOSING_TAGS = ['hi', 'foreign', 'add', 'foreign_hi', 'add_foreign_hi']

Critical = namedtuple('Critical', ['style', 'text'])

class Utils:
    def __init__(self, namespaces, text_styles):
        self.namespaces = namespaces
        self.text_styles = text_styles

    def extract_text(self, element):
        """Extract text from the element as a list of strings.

        Note that we need to preserve linebreak tags.
        """
        text = self.extract_text_recursively(element)
        text = [text_part for text_part in text if text_part]
        glued_text = []
        current_part_to_glue = []
        for text_part in text:
            if text_part != '</lb>':
                current_part_to_glue.append(text_part)
            else:
                glued_text.append(''.join(current_part_to_glue))
                glued_text.append('</lb>')
                current_part_to_glue = []
        if current_part_to_glue:
            glued_text.append(''.join(current_part_to_glue))
        return glued_text

    def extract_text_recursively(self, element):
        if len(element) == 0:
            if element.tag.endswith('line-break'):
                return ['</lb>', safe(element.tail)]
            if self.element_style_is('positioned', element):
                return ['<FN_{}>'.format(safe(element.text)), safe(element.tail)]
            return ([safe(element.text), safe(element.tail)])

        text = [safe(element.text)]
        for subelement in element:
            text.extend(self.extract_text(subelement))
        text.append(safe(element.tail))
        return text

    def extract_text_as_str(self, element):
        text_as_list = self.extract_text(element)
        text_as_str = ''.join(text_as_list)
        return text_as_str

    def tag_matches(self, tag, element):
        return re.search(tag, self.extract_text_as_str(element)) is not None

    def get_element_style_name(self, element):
        return element.get(add_namespace('style-name', self.namespaces['text']))

    def get_element_style(self, element):
        element_style_name = self.get_element_style_name(element)
        return self.text_styles.get(element_style_name, [])

    def element_style_is(self, styles_to_test, element):
        if not isinstance(styles_to_test, list):
            styles_to_test = [styles_to_test]
        element_style = self.get_element_style(element)
        return any(style in element_style for style in styles_to_test)

def add_namespace(tag, namespace):
    return ''.join(('{' + namespace + '}', tag))

def parse_arguments():
    parser = ArgumentParser(description='Try to process an input file (part of sxw)')

    parser.add_argument('-i', '--input-file', metavar='INPUT_FILE',
                        type=str, action='store',
                        default=None, dest='input_file',
                        help='input file', required=True)
    parser.add_argument('-p', '--problematic-file', metavar='PROBLEMATIC_FILE',
                        type=str, action='store',
                        default='', dest='problematic_file',
                        help='file for logging problematic comments (parsing errors)')
    parser.add_argument('-c', '--comment-file', metavar='COMMENT_FILE',
                        type=str, action='store',
                        default='', dest='comment_file',
                        help='file for lost comments')
    parser.add_argument('-a', '--apparatus-file', metavar='APPARATUS_FILE',
                        type=str, action='store',
                        default='', dest='apparatus_file',
                        help='file for lost critical apparatus entries')

    # comment progress monitoring for debug purposes
    parser.add_argument('--show-comment-merges',
                        action='store_true', default=False,
                        dest='show_comment_merges',
                        help='show how the comments are merged when attempting to repair them')
    parser.add_argument('--show-problematic-comments',
                        action='store_true', default=False,
                        dest='show_problematic_comments',
                        help='show the comments that failed to parse correctly')
    parser.add_argument('--show-comment-progress',
                        action='store_true', default=False,
                        dest='show_comment_progress',
                        help='show found and not found comments when attempting to insert them')
    parser.add_argument('--only-failed-comments',
                        action='store_true', default=False,
                        dest='only_failed_comments',
                        help='only show the comments that failed to be inserted')

    # critical apparatus tweaks
    parser.add_argument('--no-critical',
                        action='store_true', default=False,
                        dest='no_critical',
                        help='bypass parsing and inserting of critical apparatus')
    parser.add_argument('--show-critical-progress',
                        action='store_true', default=False,
                        dest='show_critical_progress',
                        help='show the progress while inserting critical apparatus entries')
    parser.add_argument('-w', '--witnesses-file', metavar='WITNESSES_FILE',
                        type=str, action='store',
                        default='', dest='witnesses_file',
                        help='file for witness entries from critical apparatus')
    parser.add_argument('--special-critical',
                        action='store_true', default=False,
                        dest='special_critical',
                        help='use special rules for parsing critical apparatus (used for Labyrint)')

    args = parser.parse_args()
    return args

def main(args):
    doc_num, namespaces, text_styles, inverse_text_styles = collect_meta(args.input_file)

    # a hack for doc number 03
    if doc_num == '03':
        text_styles['T38'] = ['italic']
        inverse_text_styles['plain'].remove('T38')
        inverse_text_styles['italic'].append('T38')

    utils = Utils(namespaces, text_styles)

    tei_tree, comments, footnotes, critical, pb_po_ed, anchor_id_template, app_id_template = transform_tree(args, text_styles, inverse_text_styles, utils, doc_num)

    pb_po_ed = default_edition_ids[doc_num]['DJAK03']

    # add witnesses
    tei_tree = add_witness(tei_tree, args.input_file)

    # add edition pagebreaks
    tei_tree, edition_page_break_numbers = add_edition_pb(tei_tree)

    # add custom styles and postprocess them
    tei_tree = add_custom_styles_pre(tei_tree)
    tei_tree = glue_custom_styles(tei_tree)

    # add foreign elements
    tei_tree = add_lang_elems_pre(tei_tree)

    # add margin elements
    tei_tree = add_margins(tei_tree)

    # collapse nested hi/foreign/add elements
    tei_tree = collapse_nested(tei_tree)

    # add comments
    tei_tree, comment_i = add_comments(args, tei_tree, comments, edition_page_break_numbers, anchor_id_template, app_id_template)

    # add footnotes
    tei_tree = add_footnotes(tei_tree, footnotes, comment_i, anchor_id_template, app_id_template)

    # add critical apparatus
    if critical:
        tei_tree, failed_critical = add_critical_apparatus(args, tei_tree, critical, edition_page_break_numbers, pb_po_ed, doc_num)
        check_critical_inside_critical(tei_tree, failed_critical)
        tei_tree = check_critical_apparatus(tei_tree)

    # expand previously collapsed nested hi/foreign/add elements
    tei_tree = expand_collapsed(tei_tree)

    # add original pagebreaks
    tei_tree = add_original_pb(tei_tree, pb_po_ed)

    # add bible references
    tei_tree = add_bible_refs(tei_tree)
    tei_tree = add_bible_refs_note(tei_tree)
    tei_tree = add_bible_refs_epigraph(tei_tree)

    # add chapters
    tei_tree = add_chapter_info(tei_tree)

    # add languages inside notes
    tei_tree = add_lang_elems_post(tei_tree)

    # add custom styles inside notes
    tei_tree = add_custom_styles_post(tei_tree)

    print('<?xml version="1.0" encoding="UTF-8"?>')
    print('<?xml-stylesheet type="text/xsl" href="DJAK.xsl"?>')
    tei_tree.getroot().attrib['xmlns'] = 'http://www.tei-c.org/ns/1.0'
    tree_as_str = ET.tostring(tei_tree, encoding='utf-8', pretty_print=True).decode('utf-8')
    tree_as_str = postprocess_as_str(tree_as_str)
    print(tree_as_str)

def postprocess_as_str(tree_as_str):
    tree_as_str = re.sub('<p>(<pb [^>]*?>)</p>', r'\1', tree_as_str)
    return tree_as_str

def strip_accents(text):
    ignore_list = '„“§†——ὐτὸςἕφαß°'
    split_text = re.split('([{}])'.format(ignore_list), text)
    split_text = [(unidecode(text_part) if text_part not in ignore_list else text_part) for text_part in split_text]
    stripped = ''.join(split_text)
    if len(text.replace('…', '...')) != len(stripped):
        print('WARNING: UNIDECODE SUCKS', file=sys.stderr)
        print(text, file=sys.stderr)
        print(stripped, file=sys.stderr)
    return stripped

def collect_meta(ifile):
    """Collect namespaces and text styles"""

    # first, collect namespaces
    namespace_dict = {}
    with open(ifile, 'r', encoding='utf-8') as input_file:
        text = input_file.read()
        root_tag_match = re.search('<office:document-content.*?>', text)
        for namespace_match in re.finditer('xmlns:(.*?)="(.*?)"', root_tag_match.group()):
            namespace_dict[namespace_match.group(1)] = namespace_match.group(2)

    properties_of_interest = [add_namespace('font-weight', namespace_dict['fo']),
                              add_namespace('font-style', namespace_dict['fo']),
                              add_namespace('letter-spacing', namespace_dict['fo']),
                              add_namespace('text-position', namespace_dict['style']),
                              add_namespace('text-underline-style', namespace_dict['style'])]
    properties_to_ignore = [add_namespace('color', namespace_dict['fo']),
                            add_namespace('font-weight-asian', namespace_dict['style']),
                            add_namespace('font-style-asian', namespace_dict['style']),
                            add_namespace('font-weight-complex', namespace_dict['style']),
                            add_namespace('font-style-complex', namespace_dict['style']),
                            add_namespace('font-size-asian', namespace_dict['style']),
                            add_namespace('font-size', namespace_dict['fo']),
                            add_namespace('font-name-asian', namespace_dict['style']),
                            add_namespace('country-asian', namespace_dict['style']),
                            add_namespace('country', namespace_dict['fo']),
                            add_namespace('font-name', namespace_dict['style']),
                            add_namespace('font-name-complex', namespace_dict['style']),
                            add_namespace('language-asian', namespace_dict['style']),
                            add_namespace('language', namespace_dict['fo']),
                            add_namespace('text-underline-width', namespace_dict['style']),
                            add_namespace('text-underline-color', namespace_dict['style']),
                            add_namespace('font-size-complex', namespace_dict['style']),
                            add_namespace('text-scale', namespace_dict['style']),
                            add_namespace('background-color', namespace_dict['fo']),
                            add_namespace('font-variant', namespace_dict['fo']),
                            add_namespace('text-transform', namespace_dict['fo']),
                            add_namespace('letter-kerning', namespace_dict['style']),
                            add_namespace('language-complex', namespace_dict['style']),
                            add_namespace('country-complex', namespace_dict['style']),
                            # Use .get() with a fallback to avoid crash if namespace is missing
                            add_namespace('rsid', namespace_dict.get('officeooo', 'urn:missing')),
                            add_namespace('char-shading-value', namespace_dict.get('loext', 'urn:missing')),
                            add_namespace('opacity', namespace_dict.get('loext', 'urn:missing')),]

    text_styles = {}
    source_tree = ET.parse(ifile)
    source_root = source_tree.getroot()

    for element in source_root:
        if (element.tag.endswith('automatic-styles')
           or element.tag.endswith('font-face-decls')
           or element.tag.endswith('font-decls')):
            for style_element in element:
                if style_element.get(add_namespace('family', namespace_dict['style'])) == 'text':
                    new_key = style_element.get(add_namespace('name', namespace_dict['style']))
                    new_value = []
                    if len(style_element) == 1:

                        if len(style_element[0].items()) == 1:
                            if (style_element[0].get(add_namespace('color', namespace_dict['fo']))
                                or style_element[0].get(add_namespace('font-name-asian', namespace_dict['style']))
                                or style_element[0].get(add_namespace('font-size-complex', namespace_dict['style']))
                                or style_element[0].get(add_namespace('font-name-complex', namespace_dict['style']))
                                or style_element[0].get(add_namespace('text-scale', namespace_dict['style']))
                                or style_element[0].get(add_namespace('rsid', namespace_dict['officeooo']))
                                or style_element[0].get(add_namespace('font-variant', namespace_dict['fo']))):
                                new_value.append('plain')
                            elif style_element[0].get(add_namespace('letter-spacing', namespace_dict['fo'])):
                                new_value.append('spaced')
                            elif style_element[0].get(add_namespace('text-position', namespace_dict['style'])):
                                new_value.append('positioned')
                            else:
                                print('Error:', style_element[0].items(), file=sys.stderr)
                            text_styles[new_key] = new_value
                        else:
                            for property_name, property_value in style_element[0].items():
                                if property_name in properties_of_interest:
                                    # collecting properties of interest
                                    if property_name == add_namespace('letter-spacing', namespace_dict['fo']):
                                        new_value.append('spaced')
                                    elif property_name == add_namespace('text-position', namespace_dict['style']):
                                        new_value.append('positioned')
                                    elif property_name == add_namespace('text-underline-style', namespace_dict['style']):
                                        if property_value == 'solid':
                                            new_value.append('spaced')
                                    else:
                                        new_value.append(property_value)
                                elif property_name in properties_to_ignore:
                                    # ignoring properties we are not interested in
                                    pass
                                else:
                                    print('Bloody strange property found:', property_name, property_value, file=sys.stderr)
                            if len(new_value) == 0:
                                new_value.append('plain')
                            text_styles[new_key] = new_value
                    else:
                        print('bad style', file=sys.stderr)

    inverse_text_styles = defaultdict(list)
    for style_name, style_values in text_styles.items():
        for value in style_values:
            inverse_text_styles[value].append(style_name)

    # we also need the document number for critical apparatus
    doc_num = re.search(r'/(\d{2})_', ifile).group(1)

    return doc_num, namespace_dict, text_styles, inverse_text_styles

def preprocess_as_text(input_file_name):
    """Do minor preprocessing of input file.

    Some things are easier to process if we treat the input
    as plain text, not as xml tree.
    """
    with open(input_file_name, 'r', encoding='utf-8') as input_file:
        text = input_file.read()

    text = text.replace('<text:s/>', ' ')
    text = text.replace('<text:soft-page-break/>', '')
    text = re.sub(r'&lt;FO(_.*?)?&gt;', '', text)
    text = re.sub(r'</?text:section.*?>', '', text)
    text = re.sub(' \| ', ' |', text)
    text = re.sub('\|', '', text)

    # with open('tmp.xml', 'w', encoding='utf-8') as tmp_file:
    #     print(text, file=tmp_file, end='')

    # os.rename('tmp.xml', args.input_file)

    # Write directly to the file instead of using os.rename (which fails in Docker volumes)
    with open(input_file_name, 'w', encoding='utf-8') as output_file:
        output_file.write(text)

def transform_tree(args, text_styles, inverse_text_styles, utils, doc_num):

    preprocess_as_text(args.input_file)
    source_tree = ET.parse(args.input_file)
    source_root = source_tree.getroot()

    problematic_file_handle = None
    if args.problematic_file:
        problematic_file_handle = open(args.problematic_file, 'w', encoding='utf-8')

    tei_tree = tei_template_maker()
    tei_root = tei_tree.getroot()

    year = None
    pages = None
    short_title = None
    date_text = None
    div, text_started = None, False
    epigraph_count = 1
    epigraph_start = epigraph_end = False
    isagoge_lat = bibl_for_sources = False
    current_page_num = None

    footnotes, reading_footnotes = {}, False
    comments, reading_comments = {}, False
    comment_i, comment_error_count = 0, 0
    critical, reading_critical = {}, False

    body_text_element = source_root.xpath('//office:body/office:text', namespaces=utils.namespaces)[0]
    for body_element in body_text_element:
        if body_element.tag.endswith('p'):
            if not text_started:
                full_text = utils.extract_text(body_element)
                matches = re.findall(r'<PE_(\d+)>', ''.join(full_text))

                if matches:
                    current_page_num = matches[-1]

                if full_text != [] and div is None and 'LÉTA' in full_text[0].upper():
                    # div is None because flag text_started does not work
                    tei_tree.xpath('//docDate/date')[0].text = ''.join(full_text)

            # stuff for teiHeader
            if utils.tag_matches('<DOC_PART_MAIN>', body_element): # 1
                short_title = utils.extract_text_as_str(body_element).replace('<DOC_PART_MAIN>', '')
                tei_tree.xpath('//text/front/titlePage/docTitle/titlePart[@type="main"]')[0].text = short_title
            elif utils.tag_matches('<DOC_SHORT_TITLE>', body_element):
                short_id = utils.extract_text_as_str(body_element).replace('<DOC_SHORT_TITLE>', '')
                anchor_id_template = 'djak3.'+ short_id.lower() + '.a-{}'
                app_id_template = '#' + anchor_id_template
            elif utils.tag_matches('<DOC_LANG>', body_element):
                language = utils.extract_text_as_str(body_element).replace('<DOC_LANG>', '')
                if 'czech' not in language:
                    if 'Dutch' in language:
                        tei_root.attrib[add_namespace('lang', xml_namespace)] = 'nl'
                    else:
                        print('Check xml language', file=sys.stderr)
            elif utils.tag_matches('<DOC_DATE>', body_element):
                date = utils.extract_text_as_str(body_element).replace('<DOC_DATE>', '')
                tei_tree.xpath('//docDate/date')[0].attrib['when'] = re.search(r'\d{4}', date).group(0)
                tei_tree.xpath('//docDate/date')[0].text = date
                pb_po_ed = date[-4:]
            elif utils.tag_matches('<DOC_EDIT>',body_element):
                value_to_transfer = utils.extract_text_as_str(body_element).replace('<DOC_EDIT>', '').upper()
                if ',' in value_to_transfer:
                    list_of_values = value_to_transfer.split(', ')
                    tei_tree.xpath('//teiHeader/fileDesc/editionStmt/respStmt/resp')[0].text = 'K vydání připravili'
                    tei_tree.xpath('//teiHeader/fileDesc/editionStmt/respStmt/name')[0].text = list_of_values[0].strip()
                    for i, val in enumerate(list_of_values[1:]):
                        name = ET.XML('<name />')
                        name.text = val.strip()
                        tei_tree.xpath('//teiHeader/fileDesc/editionStmt/respStmt[1]')[0].insert(i+2, name)    
                else:    
                    tei_tree.xpath('//teiHeader/fileDesc/editionStmt/respStmt/name')[0].text = value_to_transfer
            elif utils.tag_matches('<DOC_RANGE>', body_element):
                pages = 's. ' + utils.extract_text_as_str(body_element).replace('<DOC_RANGE>', '')
            elif utils.tag_matches('<DOC_PUBLISHED>', body_element):
                year = ' ' + utils.extract_text_as_str(body_element).replace('<DOC_PUBLISHED>', '') + ', '
            elif utils.tag_matches('<DOC_(LANG|TYPE|VOLUME|ORDER|SHORT_TITLE)>', body_element): # 2
                pass
            elif pages is not None and year is not None:
                value_to_transfer = year + pages
                tei_tree.xpath('//teiHeader/fileDesc/publicationStmt/p/bibl')[0].text += value_to_transfer
                pages = None
                year = None
            elif utils.tag_matches('<DOC_TITLE>', body_element): # 3
                title = utils.extract_text_as_str(body_element).replace('<DOC_TITLE>', '').strip()
                tei_tree.xpath('//teiHeader/fileDesc/titleStmt/title')[0].text = title
            elif utils.tag_matches('<DOC_PART_DESC>', body_element): # 4
                desc_element = tei_tree.xpath('//text/front/titlePage/docTitle/titlePart[@type="desc"]')[0]
                desc = utils.extract_text(body_element)
                add_text(desc_element, desc, remove_text='<DOC_PART_DESC>')

            elif utils.tag_matches('<EPIGRAPH>', body_element):
                epigraph_start = True
                epigraph_end = False
                epigraph_text = utils.extract_text(body_element)
                epigraph = ET.XML('<epigraph />')
                quot = ET.SubElement(epigraph, 'q')
                tei_tree.xpath('//text/front/titlePage[1]')[0].insert(epigraph_count, epigraph)
                inserted_quots_num = 0

                if not utils.tag_matches('</EPIGRAPH>', body_element):
                    add_text(quot, epigraph_text, remove_text='<EPIGRAPH>')

                else:
                    epigraph_start = False
                    epigraph_end = True
                    add_text(quot, epigraph_text, remove_text=['<EPIGRAPH>', '</EPIGRAPH>'])
                    epigraph_count += 1

            elif utils.tag_matches('</EPIGRAPH>', body_element):
                epigraph_start = False
                epigraph_end = True
                epigraph_text = utils.extract_text(body_element)
                inserted_quots_num += 1
                quot = ET.XML('<q />')
                add_text(quot, epigraph_text, remove_text='</EPIGRAPH>')
                tei_tree.xpath('//text/front/titlePage[1]/epigraph[{}]'.format(epigraph_count))[0].insert(inserted_quots_num, quot)
                epigraph_count += 1

            elif not epigraph_end and epigraph_start and len(body_element) != 0:
                epigraph_text = utils.extract_text(body_element)
                inserted_quots_num += 1
                quot = ET.XML('<q />')
                add_text(quot, epigraph_text)
                tei_tree.xpath('//text/front/titlePage[1]/epigraph[{}]'.format(epigraph_count))[0].insert(inserted_quots_num, quot)

            elif reading_comments:
                if 'KOMENTÁŘ' in utils.extract_text_as_str(body_element):
                    continue
                if 'APPARATUS' in utils.extract_text_as_str(body_element):
                    if args.no_critical:
                        print('Encountered {} problematic comment(s)'.format(comment_error_count), file=sys.stderr)
                        return tei_tree, comments, footnotes, critical, pb_po_ed, anchor_id_template, app_id_template

                    # cut off at the start of critical notes
                    reading_comments = False
                    reading_critical = True
                    if args.witnesses_file:
                        witnesses_file = open(args.witnesses_file, 'w', encoding='utf-8')
                    else:
                        witnesses_file = None
                    continue

                # look for comment page num
                match = re.match(r'<PEko_(\d+)>', ''.join(utils.extract_text(body_element)), flags=re.I)
                if match is not None:
                    comment_page = match.group(1)
                    comments[comment_page] = []
                elif len(body_element) >= 1:
                    # skip paragraphs that are completely empty to avoid index errors
                    if re.match(r'<PE(ko)?_\d+>', safe(body_element[0].text)) is not None and len(body_element) == 1:
                        continue

                    # clean and transform the subtree
                    # remove empty subelements
                    for subelement in body_element:
                        if element_is_empty(subelement) or re.match('^<PE_\d+> ?$', utils.extract_text_as_str(subelement)):
                            body_element.remove(subelement)
                        elif tail_is_empty(subelement):
                            subelement.tail = ''

                    for subelement in body_element:
                        if subelement.tag.endswith('s'):
                            body_element.remove(subelement)
                            continue

                    # repair <LAT>, <GREEK>, <GER>, etc.
                    foreign = None
                    prev_subelement = None
                    for subelement in body_element:
                        if foreign is not None:
                            subelement.text = '<{}>{}'.format(foreign, subelement.text)
                            prev_subelement = subelement
                            foreign = None
                        elif re.search(r'<(LAT|GREEK|GER|CZECH)>', subelement.text):
                            body_element.remove(subelement)
                            foreign = re.search(r'<(LAT|GREEK|GER|CZECH)>', subelement.text).group(1)
                        elif re.search(r'</(LAT|GREEK|GER|CZECH)>', subelement.text):
                            body_element.remove(subelement)
                            foreign = re.search(r'</(LAT|GREEK|GER|CZECH)>', subelement.text).group(1)
                            prev_subelement.text = '{}</{}>'.format(prev_subelement.text, foreign)
                            prev_subelement = None
                            foreign = None

                    # fix s p a c e d
                    prev_spaced = False
                    prev_subelement = None
                    for subelement in body_element:
                        if utils.element_style_is('spaced', subelement):
                            if prev_subelement is not None and utils.element_style_is(PLAIN_STYLE, prev_subelement):
                                # Preserve tail
                                separator = prev_subelement.tail if prev_subelement.tail else ''
                                prev_subelement.text = ''.join((prev_subelement.text, separator, '<REND_SP>', subelement.text, '</REND_SP>'))
                                body_element.remove(subelement)
                            else:
                                prev_spaced = True
                                prev_subelement = subelement
                        elif prev_spaced:
                            if utils.element_style_is(PLAIN_STYLE, subelement):
                                # Preserve tail
                                separator = prev_subelement.tail if prev_subelement.tail else ''
                                subelement.text = ''.join(('<REND_SP>', prev_subelement.text, '</REND_SP>', separator, subelement.text))
                                body_element.remove(prev_subelement)
                            prev_spaced = False
                            prev_subelement = subelement

                    # Pre-merge "Italic + Space + Italic" sequences into a single Italic element.
                    i = 0
                    while i < len(body_element) - 2:
                        current = body_element[i]
                        next_1 = body_element[i+1]
                        next_2 = body_element[i+2]

                        # Check: Italic + (Space/Plain) + Italic
                        if (utils.element_style_is('italic', current) and 
                            utils.element_style_is(PLAIN_STYLE, next_1) and 
                            utils.element_style_is('italic', next_2) and
                            next_1.text == ' '): 

                            # Merge all three into 'current'
                            current.text = (current.text or '') + ' ' + (next_2.text or '')
                            current.tail = next_2.tail 

                            body_element.remove(next_1)
                            body_element.remove(next_2)
                        else:
                            i += 1

                    for i in range(len(body_element) - 1, -1, -1):
                        sub = body_element[i]
                        # If it is a space/plain style AND consists only of whitespace
                        if (utils.element_style_is(PLAIN_STYLE, sub) and 
                            sub.text and sub.text.strip() == '' and 
                            tail_is_empty(sub)):
                            # If it's the first element (before the Number), just remove it
                            if i == 0:
                                body_element.remove(sub)
                            # If it's between elements, try to merge the space into the previous element's text
                            elif i > 0:
                                prev = body_element[i-1]
                                prev.text = (prev.text or '') + (sub.text or '')
                                body_element.remove(sub)

                    # skip paragraphs that became empty after cleaning
                    if len(body_element) == 0:
                        continue
                    # merge elements with same style if there is no tail between them
                    # or if the second one is empty but has a tail
                    prev_subelement = body_element[0]
                    for subelement in body_element[1:]:
                        if utils.get_element_style(subelement) == utils.get_element_style(prev_subelement):
                            if tail_is_empty(prev_subelement):
                                # merge previous element into current
                                if args.show_comment_merges:
                                    print('Merging:', file=sys.stderr)
                                    print(utils.get_element_style_name(prev_subelement), prev_subelement.text, file=sys.stderr)
                                    print(utils.get_element_style_name(subelement), subelement.text, file=sys.stderr)
                                
                                # Preserve the tail (space) of the previous element if it exists
                                separator = prev_subelement.tail if prev_subelement.tail else ''
                                subelement.text = (prev_subelement.text or '') + separator + (subelement.text or '')
                                
                                if args.show_comment_merges:
                                    print('Result:', file=sys.stderr)
                                    print(utils.get_element_style_name(subelement), subelement.text, file=sys.stderr)
                                    print(file=sys.stderr)
                                body_element.remove(prev_subelement)
                                prev_subelement = subelement
                            elif text_is_empty(subelement) and not tail_is_empty(subelement):
                                # merge current element's tail into previous element's
                                if args.show_comment_merges:
                                    print('Merging:', file=sys.stderr)
                                    print(utils.get_element_style_name(prev_subelement), prev_subelement.tail, file=sys.stderr)
                                    print(utils.get_element_style_name(subelement), subelement.tail, file=sys.stderr)
                                
                                # Use empty string join, but careful about existing spaces
                                prev_subelement.tail = (prev_subelement.tail or '') + (subelement.tail or '')
                                
                                if args.show_comment_merges:
                                    print('Result:', file=sys.stderr)
                                    print(utils.get_element_style_name(prev_subelement), prev_subelement.tail, file=sys.stderr)
                                    print(file=sys.stderr)
                                body_element.remove(subelement)
                        else:
                            prev_subelement = subelement

                    # remove last element if it contains page break
                    if re.match(r'<PE(ko)?_\d+>', str(body_element[-1].text)) is not None:
                        body_element.remove(body_element[-1])

                    comment_i += 1
                    # parse known templates

                    # template 1a: bold.text (missing), italic.text, italic.tail
                    # (formerly [T4.text], T5.text, T5.tail)
                    if (len(body_element) == 1
                        and utils.element_style_is('italic', body_element[0])):
                        number = '???'
                        label_text = body_element[0].text
                        note_text = body_element[0].tail

                    # template 1b: bold.text, italic.text, italic.tail
                    # formerly T4.text, T5.text, T5.tail
                    elif (len(body_element) == 2
                          and utils.element_style_is('bold', body_element[0])
                          and utils.element_style_is('italic', body_element[1])):
                        number = body_element[0].text
                        label_text = body_element[1].text
                        note_text = body_element[1].tail

                    # template 2: bold.text, italic.text, plain.text
                    # (formerly T1.text, T3.text, T2.text)
                    elif (len(body_element) >= 3
                          and utils.element_style_is('bold', body_element[0])
                          and utils.element_style_is('italic', body_element[1])):
                        
                        number = body_element[0].text
                        label_text = body_element[1].text
                        
                        # Merge all remaining elements into the note text, regardless of style
                        note_parts = []
                        for elem in body_element[2:]:
                            note_parts.append(elem.text or '')
                            note_parts.append(elem.tail or '')
                        note_text = ''.join(note_parts)

                    # something unexpected that needs more extensive repairs
                    else:
                        msg = 'Problematic comment for page {}\n'.format(comment_page)
                        for subelement in body_element:
                            msg += '{} "{}"/"{}"\n'.format(
                                utils.get_element_style_name(subelement),
                                subelement.text, subelement.tail)
                        msg += '\n'

                        if args.show_problematic_comments:
                            print(msg, file=sys.stderr)

                        if problematic_file_handle:
                            problematic_file_handle.write(msg)

                        comment_error_count += 1
                        continue

                    label_text = re.sub(r'\s{2,}', ' ', label_text.strip())
                    label_text = re.sub(r'\s\)', ')', label_text)

                    # if everything went well, add parsed comment to the dict
                    comments[comment_page].append((number, label_text, note_text, comment_i))

            elif reading_critical:
                # look for comment page num
                current_wits = None
                match = re.match(r'<PEka_(\d+)>', utils.extract_text_as_str(body_element), flags=re.I)
                if match is not None:
                    critical_page = match.group(1)
                    critical[critical_page] = []
                    critical_element = []
                elif len(body_element) >= 1:
                    if len(body_element) > 1:
                        prev_sub = body_element[0]
                        for sub in body_element[1:]:
                            if (utils.get_element_style(sub) == utils.get_element_style(prev_sub) and 
                                tail_is_empty(prev_sub)):
                                prev_sub.text = (prev_sub.text or '') + (sub.text or '')
                                body_element.remove(sub)
                            else:
                                prev_sub = sub

                    for subelement in body_element:
                        candidate = safe(subelement.text).strip()
                        if args.special_critical and candidate and candidate in 'abc' and utils.element_style_is('bold', subelement):
                            current_wits = labyrint_wits[candidate]

                        elif re.match('[—–] \d+', safe(subelement.text)) is not None:
                            number = safe(subelement.text).split()[1]
                            critical_element = format_critical(critical_element, doc_num, witnesses_file, wits=current_wits)
                            if critical_element is not None:
                                critical[critical_page].append(critical_element)
                            critical_element = [(None, number)]

                        elif re.search('[—–]', safe(subelement.text)) is not None:
                            subelement.text = re.sub('[—–]', '', subelement.text).strip()
                            
                            if (utils.element_style_is('italic', subelement)
                                and not utils.element_style_is('bold', subelement)):
                                style = 'italic'
                            else:
                                style = None

                            critical_element.append((style, subelement.text))

                            if args.special_critical:
                                current_wits = check_special_critical_wit(critical_element, current_wits)
                            
                            critical_element = format_critical(critical_element, doc_num, witnesses_file, wits=current_wits)
                            if critical_element is not None:
                                critical[critical_page].append(critical_element)
                            critical_element = []
                        else:
                            if not text_is_empty(subelement):
                                # for italics
                                if (utils.element_style_is('italic', subelement)
                                    and not utils.element_style_is('bold', subelement)):
                                    style = 'italic'
                                else:
                                    style = None
                                critical_element.append((style, subelement.text))
                            if not tail_is_empty(subelement):
                                critical_element.append((None, subelement.tail))

                    if critical_element:
                        if args.special_critical:
                            current_wits = check_special_critical_wit(critical_element, current_wits)

                        critical_element = format_critical(critical_element, doc_num, witnesses_file, wits=current_wits)
                        if critical_element is not None:
                            critical[critical_page].append(critical_element)
                        critical_element = []

            elif div is None:
                text = utils.extract_text(body_element)
                if utils.tag_matches('<TEXT_START>', body_element):
                    body = tei_tree.xpath('//body')[0]
                    div = ET.SubElement(body, 'div')
                    p = ET.SubElement(div, 'p')
                    p.text = '<PE_' + current_page_num + '>'
                    head = ET.SubElement(div, 'head')
                    add_text(head, text)
                    head.text = head.text.replace('<TEXT_START>', '')
                elif utils.tag_matches('<TEXT_START_NP>', body_element):
                    body = tei_tree.xpath('//body')[0]
                    div = ET.SubElement(body, 'div')
                    p = ET.SubElement(div, 'p')
                    p.text = '<PE_' + current_page_num + '>'
                    head = ET.SubElement(div, 'p')
                    add_text(head, text)
                    head.text = head.text.replace('<TEXT_START_NP>', '')

            elif '<ISAGOGE' in utils.extract_text_as_str(body_element):
                # 1. Get the full text of the paragraph first
                full_p_text = utils.extract_text_as_str(body_element)
                
                # 2. Determine which tag we are dealing with
                is_lat = '<ISAGOGE_LAT>' in full_p_text
                
                if not is_lat:
                    text = tei_tree.xpath('//text')[0]
                    back = ET.SubElement(text, 'back')
                
                div = ET.SubElement(back, 'div')
                div.attrib['type'] = 'note'
                
                if is_lat:
                    reading_footnotes = False
                    div.attrib[add_namespace('lang', xml_namespace)] = 'la'
                    isagoge_lat = True
                    tag_to_remove = '<ISAGOGE_LAT>'
                else:
                    tag_to_remove = '<ISAGOGE>'

                head = ET.SubElement(div, 'head')
                
                # 3. Instead of relying on body_element[1], just clean the string we extracted at the start
                clean_title = full_p_text.replace(tag_to_remove, '').strip()
                
                # Remove any initial line breaks or punctuation if present
                clean_title = re.sub(r'^(\s|</lb>)+', '', clean_title)
                
                head.text = clean_title

            elif reading_footnotes:
                if len(body_element) == 2:
                    footnote_number = body_element[0].text
                    footnote_text = body_element[1].text
                    footnotes[footnote_number] = footnote_text.lstrip()

            elif div is not None:
                # catch T6 (spaced style)
                for subelement in body_element:
                    if utils.element_style_is('spaced', subelement):
                        subelement.text = '<REND_SP>' + subelement.text + '</REND_SP>'
                    elif (utils.element_style_is('italic', subelement)
                          and len(utils.extract_text_as_str(subelement)) > 4):
                        subelement.text = '<REND_I>' + subelement.text + '</REND_I>'
                p_text = utils.extract_text(body_element)

                if not p_text:
                    continue

                if utils.tag_matches('<COMMENTARY>', body_element) or utils.tag_matches('KOMENTÁŘ', body_element):
                    # start parsing comments
                    reading_comments = True
                    comment_page = None
                    page_comments = []
                    continue

                elif utils.tag_matches('<FOOTNOTES>', body_element):
                    reading_footnotes = True
                    continue

                elif re.search('<CHAPTER>|<SOURCES>|<PREFACE(?:_.*?)>|PŘEDMLUVA|'
                               'ZAVÍRKA|ZÁVĚREK|POŘÁDEK|MODLITBA',
                               ''.join(p_text)) is not None:

                    if '<SOURCES>' in p_text[0]:
                        div = ET.SubElement(back, 'div')
                        bibl_for_sources = True
                        p_text[0] = p_text[0].replace('<SOURCES>', '')

                    p = ET.SubElement(div, 'head')
                    # don't remove the text tag, we'll need it later
                    
                elif not isagoge_lat and bibl_for_sources:
                    p = ET.SubElement(div, 'bibl')
                else:
                    p = ET.SubElement(div, 'p')

                add_text(p, p_text)

    if args.special_critical:
        # try matching critical apparatus
        from collections import OrderedDict
        for apparatus_page in critical:
            # divide
            separated = OrderedDict()
            for entry in critical[apparatus_page]:
                entry_wit = entry[2][0][0]
                separated.setdefault(entry_wit, [])
                separated[entry_wit].append(entry)
            separated = list(separated.values())

            # conquer
            merged = separated[0]
            for merging in separated[1:]:
                appending = []
                for merging_candidate in merging:
                    lemma_text = merging_candidate[1][0][1]
                    for i, merge_candidate in enumerate(merged):
                        if merging_candidate[0] == merge_candidate[0] and lemma_text == merge_candidate[1][0][1]:
                            for j, merge_rdg in enumerate(merge_candidate[2]):
                                if merge_rdg[1] == merging_candidate[2][0][1]:
                                    merged_rdg = (' '.join((merge_rdg[0], merging_candidate[2][0][0])),) + merge_rdg[1:]
                                    merged_rdg_list = merge_candidate[2][:j] + (merged_rdg,) + merge_candidate[2][j+1:]
                                    merged[i] = merge_candidate[:2] + (merged_rdg_list,)
                                    break
                            else:
                                merged[i] = merge_candidate[:2] + ((merge_candidate[2] + merging_candidate[2]),)
                            break
                    else:
                        appending.append(merging_candidate)
                merged.extend(appending)
            critical[apparatus_page] = merged

    print('Encountered {} problematic comment(s)'.format(comment_error_count), file=sys.stderr)
    if witnesses_file is not None:
        witnesses_file.close()
    if problematic_file_handle:
        problematic_file_handle.close()
    return tei_tree, comments, footnotes, critical, pb_po_ed, anchor_id_template, app_id_template

def check_special_critical_wit(critical_element, current_wits):
    if critical_element[0][1] in 'abc':
        current_wits = labyrint_wits[critical_element[0][1]]
        critical_element.pop(0)
    return current_wits

def preformat_critical(critical_element):
    critical_element = [((None, ']') if re.match(r'\] ?', part[1]) is not None else part) for part in critical_element]

    if not critical_element[0][1].strip().isdigit():
        if critical_element[0][1].strip().split()[0].isdigit():
            split = critical_element[0][1].strip().split()
            critical_element = [(None, split[0]), (None, split[1])] + critical_element[1:]
        else:
            return None

    try:
        split_i = critical_element.index((None, ']'))
    except ValueError:
        print('No ] in critical element', file=sys.stderr)
        print(critical_element, file=sys.stderr)
        return None
        
    if split_i == len(critical_element) - 1:
        print('No rdg part in critical element', file=sys.stderr)
        print(critical_element, file=sys.stderr)
        return None

    before = critical_element[1:split_i]
    before = [(elem[0], elem[1].strip()) for elem in before]

    after = critical_element[split_i+1:]
    after = [elem for elem in after if elem != (None, '')]
    after[0] = (after[0][0], after[0][1].lstrip())
    after[-1] = (after[-1][0], after[-1][1].rstrip())

    return int(critical_element[0][1]), before, after

def repair_italics_in_critical(after):

    corrected_after = []
    current = after[0]

    for i, element in enumerate(after[1:]):
        if current[0] == 'italic' and element[0] is None and element[1] == ' ' and i < len(after) - 1 and after[i+1][0] == 'italic':
            current = ('italic', current[1] + ' ')
        elif element[0] == 'italic' or re.match('^[.,] ?$', element[1]) is not None:
            if current[0] != 'italic':
                corrected_after.append(current)
                current = element
            else:
                current = ('italic', re.sub(' ?([.,])', r'\1', ' '.join((current[1], element[1]))))
        else:
            if current[0] == 'italic':
                if element[1].startswith(', '):
                    current = (current[0], current[1] + ', ')
                    element = (element[0], re.sub('^, ', '', element[1]))
                corrected_after.append(current)
                current = element
            else:
                current = (None, ' '.join((current[1], element[1])))

    corrected_after.append(current)
    corrected_after = [(elem[0], re.sub('([.,]) *', r'\1 ', elem[1])) for elem in corrected_after]
    if len(corrected_after) > 0 and not corrected_after[-1][1].strip():
        corrected_after = corrected_after[:-1]

    return corrected_after

    if corrected_after != after:
        print('=' * 75, file=sys.stderr)
        print('Before:', file=sys.stderr)
        print(before, file=sys.stderr)
        print(after, file=sys.stderr)
        print('-' * 75, file=sys.stderr)

        print('After:', file=sys.stderr)
        print(corrected_after, file=sys.stderr)
        print('=' * 75, file=sys.stderr)
        after = corrected_after

    return before, after

def parse_wits(wit_str, doc_num, position='a', add_default=True):
    parsed_wits = []
    if add_default:
        parsed_wits.append('#DJAK03')

    wit_list = re.split('[,a]', wit_str)

    for wit in wit_list:
        wit = wit.strip().strip(';')
        if wit:
            ed_wit = edition_ids[doc_num].get(wit)
            if ed_wit is not None:
                wit = '#' + ed_wit
            else:
                wit = '[tbd_{}: {}]'.format(position, wit)
            parsed_wits.append(wit)
    return ' '.join(parsed_wits)

def extract_witnesses_left(before, doc_num, witnesses_file):

    # easy case: only one piece, use default witness
    if len(before) == 1 and before[0][0] is None:
        return [('#DJAK03', before[0][1], 'lem')]

    # a placeholder
    if len(before) == 1 and before[0][0] == 'italic':
        return [('#DJAK03', before[0][1], 'lem')]

    return [(parse_wits(before[1][1], doc_num), before[0][1], 'lem')]

def extract_witnesses_right(after, doc_num, witnesses_file):

    # easy case: only one piece, use default witness
    if len(after) == 1 and after[0][0] is None:
        return [('#' + default_edition_ids[doc_num]['DJAK03'], after[0][1])]

    # no text(?), some witness extraction needed
    if len(after) == 1 and after[0][0] == 'italic':
        return [('tbd', after[0][1])]

    # now we need more thorough check
    next_style_dict = {None: 'italic', 'italic': None}
    counts = {None: 0, 'italic': 0}
    prev_style = after[0][0]
    counts[prev_style] += 1
    for elem in after[1:]:
        current_style = elem[0]
        counts[current_style] += 1
        if current_style != next_style_dict[prev_style]:
            return [('unparsed', ' | '.join([piece[1].strip() for piece in after]))]
        prev_style = current_style
    if counts[None] != counts['italic']:
        return [('unparsed', ' | '.join([piece[1].strip() for piece in after]))]

    # this is one of the two typical set-ups:
    # starts with the actual text followed by withess(es), which then alternate
    extracted_after = []
    if after[0][0] is None:
        for text, wits in zip(after[:-1:2], after[1::2]):
            extracted_after.append((parse_wits(wits[1], doc_num, add_default=False), text[1]))
        return extracted_after

    # this is another one of the two typical set-ups,
    # which is the reverse of the above
    extracted_after = []
    if after[0][0] == 'italic':
        for text, wits in zip(after[1::2], after[:-1:2]):
            extracted_after.append((parse_wits(wits[1], doc_num, position='b', add_default=False), text[1]))
        return extracted_after

def format_critical(critical_element, doc_num, witnesses_file, wits=None):
    preformatted = preformat_critical(critical_element)
    if preformatted is None:
        return None

    num, before, after = preformatted

    before = repair_italics_in_critical(before)
    after = repair_italics_in_critical(after)

    if wits is None:
        before = extract_witnesses_left(before, doc_num, witnesses_file)
        after = extract_witnesses_right(after, doc_num, witnesses_file)
    else:
        before = [(wits[0], before[0][1], 'lem')]
        after = [(wits[1], after[0][1])]

    if after is None:
        return None

    return (num, tuple(before), tuple(after))

def safe(text):
    return '' if text is None else text

def text_is_empty(element):
    return element.text is None or element.text.strip() == ''

def tail_is_empty(element):
    return element.tail is None or element.tail.strip() == ''

def element_is_empty(element):
    return text_is_empty(element) and tail_is_empty(element)

def add_text(element, text, remove_text=None):
    if remove_text is not None and not isinstance(remove_text, list):
        remove_text = [remove_text]

    element.text = text[0]
    if remove_text is not None:
        for remove_text_piece in remove_text:
            element.text = element.text.replace(remove_text_piece, '')
    for part in text[1:]:

        if part == '</lb>':
            lb = ET.SubElement(element, 'lb')
        else:
            if remove_text is not None:
                for remove_text_piece in remove_text:
                    part = part.replace(remove_text_piece, '')
            lb.tail = part

def add_edition_pb(tei_tree):
    # add edition page breaks
    edition_page_break_numbers = []  # for keeping track of what we've found
    for elem in tei_tree.xpath('//text/*[self::body or self::back]/div[1]/p'):
        # check for edition page break
        # suddenly, there can be more than one inside one <p>
        # we need to get PE and all text either till next PE
        # or till the end of the <p> text
        current = None
        for pe_match in re.finditer(r'(.*?)(?:\| ?)?<PE_(\d+)>(.*?)(?=<PE_\d+>|$)', str(elem.text)):
            text_before, pe_number, text_after = pe_match.groups()
            pb_elem = ET.SubElement(elem, 'pb')
            pb_elem.attrib['n'] = pe_number
            pb_elem.attrib['ed'] = pb_pe_ed
            pb_elem.tail = text_after
            if current is None:
                elem.text = text_before
                current = pb_elem
            else:
                current.tail += text_before
            edition_page_break_numbers.append(pe_number)

    # remove PE where they don't belong
    for elem in tei_tree.iter():
        if elem.text is not None:
            elem.text = re.sub(r'(?:\| ?)?<PE_(\d+)>', '', elem.text)
        if elem.tail is not None:
            elem.tail = re.sub(r'(?:\| ?)?<PE_(\d+)>', '', elem.tail)

    return tei_tree, edition_page_break_numbers

def create_label_regex(label):
    """Create regex for label.
    Updated to handle glued XML text AND normal text by making whitespace fully optional.
    """
    # 1. Clean weird hidden characters
    stripped_label = label.strip().replace(b'\xc2\xad'.decode(), '')
    stripped_label = strip_accents(stripped_label)
    
    if '…' in stripped_label:
        print(stripped_label, file=sys.stderr)

    stripped_label = stripped_label.replace('. . .', '...')

    # 2. Handle ellipsis fuzzy matching
    label_regex_string = re.sub(r'(?<=\w)(\.{3,} ?|\.{2,} \.+ ?|\. \.{2,} ?)', r'\\b.*?', stripped_label)
    label_regex_string = re.sub(r'(\.{3,} ?|\.{2,} \.+ ?|\. \.{2,} ?)', r'.*?', label_regex_string)
    
    parts = [part for part in re.split(r'(</?LAT>|(?:\\b)?\.\*\?)', label_regex_string) if part]
    new_parts = []
    
    # Robust Joiner. Matches 0+ spaces OR Page Breaks.
    # We use (?: ... )* for non-capturing group, repeating.
    joiner = r'(?: |\|?<PO_\d+>)*'
    
    for part in parts:
        if re.match(r'(</?LAT>|(?:\\b)?\.\*\?)', part) is None:
            # Remove spaces from the label text, then inject the permissive joiner between every char.
            clean_part = part.replace(' ', '')
            
            # This turns "mne" into "m[space/tag]*n[space/tag]*e"
            new_parts.append(joiner.join([re.escape(p) for p in list(clean_part)]))
        else:
            new_parts.append(part)
        label_regex_string = ''.join(new_parts)

    # add possibility for punctuation and/or original pagebreak at the end
    label_regex_string_parts = [part for part in re.split('(</?LAT>)', label_regex_string) if part]
    if not label_regex_string_parts:
        return re.compile("IMPOSSIBLE_MATCH_PLACEHOLDER")

    if label_regex_string_parts[0] == '<LAT>':
        label_regex_string_parts[0] = r'<LAT>[„"]?'
    else:
        label_regex_string_parts = [r'[„"]?'] + label_regex_string_parts
        
    if label_regex_string_parts[-1] == '</LAT>':
        label_regex_string_parts[-1] = r'[,.:;?!]?</LAT>'
    else:
        label_regex_string_parts = label_regex_string_parts + [r'[,.:;?!]?']
        
    label_regex_string = ''.join(label_regex_string_parts)

    label_regex_string = re.sub(r'(.*?)(\w)(\[,\.:;\?!\]\?)(.*)', r'\1\2\\b\3\4', label_regex_string)

    if re.match(r'^\w', stripped_label):
        label_regex_string = r'\b' + label_regex_string
    if re.match(r'.*\w$', stripped_label):
        label_regex_string = label_regex_string + r'\b'

    label_regex = re.compile(label_regex_string, flags=re.I)
    return label_regex

def add_comments(args, tei_tree, comments, edition_page_break_numbers, anchor_id_template, app_id_template):
    """Insert comments into the document."""

    if args.comment_file:
        comment_file = open(args.comment_file, 'w', encoding='utf-8')

    comment_failure_count = 0
    active_page_break_numbers = sorted(set(edition_page_break_numbers) & set(comments))
    comment_i = 0

    for pe_number in active_page_break_numbers:
        # Track anchors we create to handle duplicates vs nesting
        # Dictionary mapping: anchor_element -> label_text
        created_anchors = {}

        if args.show_comment_progress and not args.only_failed_comments:
            print('Adding comments for page {}'.format(pe_number), end='\n\n', file=sys.stderr)

        pagebreaks = tei_tree.xpath('//text/*[self::body or self::back]/div[1]/p/pb[@n="{}"]'.format(pe_number))
        if not pagebreaks:
            print('Couldn\'t find pagebrake {}'.format(pe_number))
            continue

        def get_sort_key(comment_tuple):
            try:
                line_num = int(re.search(r'\d+', comment_tuple[0]).group())
            except (ValueError, AttributeError, TypeError):
                line_num = 99999
            length_score = -len(comment_tuple[1])
            original_index = comment_tuple[3]
            return (line_num, length_score, original_index)

        sorted_comments = sorted(comments[pe_number], key=get_sort_key)

        for number, label, note, comment_i in sorted_comments:
            start = current = pagebreaks[0]
            current_p = current.getparent()

            label_regex = create_label_regex(label)
            found_and_placed = False

            while current_p is not None and not found_and_placed:
                
                # Check 1: Text appearing BEFORE the current tag (e.g. before a Page Break)
                if current is not None and len(current_p) > 0 and current == current_p[0] and current_p.text:
                    label_match = label_regex.search(strip_accents(safe(current_p.text)))
                    if label_match is not None:
                        # Pre-text check doesn't involve anchors, so safe to insert
                        if args.show_comment_progress and not args.only_failed_comments:
                            print('Found "{}" in "{}" (Pre-tag)'.format(label, current_p.text), end='\n\n', file=sys.stderr)
                        
                        new_anchor = add_comment(current_p, label_match, comment_i, label, note, anchor_id_template, app_id_template, current=None)
                        created_anchors[new_anchor] = label
                        found_and_placed = True
                        break

                if current is not None:
                    # Check 2: Text inside an element (ENCLOSING_TAGS)
                    if current.tag in ENCLOSING_TAGS:
                        label_match = label_regex.search(strip_accents(safe(current.text)))
                        if label_match is not None:
                            # Smart Skip for Duplicates
                            # If we matched inside an anchor we created, and it's the exact same label...
                            if (current in created_anchors and 
                                created_anchors[current] == label and 
                                label_match.start() == 0):
                                # It's a duplicate match (e.g. "nebo" matching "nebo"). Skip to find the next one.
                                pass 
                            else:
                                if args.show_comment_progress and not args.only_failed_comments:
                                    print('Found "{}" in "{}"'.format(label, current.text), end='\n\n', file=sys.stderr)

                                new_anchor = add_comment(current, label_match, comment_i, label, note, anchor_id_template, app_id_template)
                                created_anchors[new_anchor] = label
                                found_and_placed = True
                                break

                    # Check 3: Text in the TAIL of the current element (Most common)
                    label_match = label_regex.search(strip_accents(safe(current.tail)))
                    if label_match is not None:
                        # Smart Skip for Duplicates
                        # If 'current' is an anchor we created, and the match is at the very start...
                        if (current in created_anchors and 
                            created_anchors[current] == label and 
                            label_match.start() == 0):
                            
                            # It is the exact same label we just inserted. 
                            # We must SKIP this match to find the *second* occurrence of the word.
                            pass
                        else:
                            # It is either a new match, OR a nested comment (different label), OR later in the string.
                            if args.show_comment_progress and not args.only_failed_comments:
                                print('Found "{}" in "{}"'.format(label, current.tail), end='\n\n', file=sys.stderr)

                            new_anchor = add_comment(current_p, label_match, comment_i, label, note, anchor_id_template, app_id_template, current=current)
                            created_anchors[new_anchor] = label
                            found_and_placed = True
                            break
                    
                    # Advance cursor
                    current = current.getnext()
                    if current is None:
                        current_p = current_p.getnext()
                        current = None
                        # Reset start for next paragraph if needed (not strictly used logic here but good practice)
                    elif current.tag == 'pb':
                        current_p = None
                else:
                    # Check 4: Text in the Paragraph itself (no children left)
                    label_match = label_regex.search(strip_accents(safe(current_p.text)))
                    if label_match is not None:
                        if args.show_comment_progress and not args.only_failed_comments:
                            print('Found "{}" in "{}"'.format(label, current_p.text), end='\n\n', file=sys.stderr)

                        new_anchor = add_comment(current_p, label_match, comment_i, label, note, anchor_id_template, app_id_template, current=current)
                        created_anchors[new_anchor] = label
                        found_and_placed = True
                        break
                    elif len(current_p) > 0:
                        current = current_p[0]
                        if current.tag == 'pb':
                            current_p = None
                    else:
                        current_p = current_p.getnext()
            
            if not found_and_placed:
                comment_failure_count += 1
                if args.show_comment_progress:
                    print('"{}" on page {} not found'.format(label, pe_number), end='\n\n', file=sys.stderr)
                if args.comment_file:
                    dud_comment = create_dud_comment(comment_i, label, note, anchor_id_template, app_id_template)
                    print('Page {}: {}'.format(pe_number, dud_comment), file=comment_file)

    print('Failed to place {} comments'.format(comment_failure_count),
          'out of {}'.format(sum(map(len, comments.values()))), file=sys.stderr)

    if args.comment_file:
        comment_file.close()

    return tei_tree, comment_i

def add_comment(current_parent, label_match, comment_i, label_text, note_text, anchor_id_template, app_id_template, current=None, note_type='gloss'):
    anchor = ET.XML('<anchor />')
    anchor.attrib[add_namespace('id', xml_namespace)] = anchor_id_template.format(comment_i)

    if note_type == 'gloss':
        app = ET.XML('<app />')
        app.attrib['from'] = app_id_template.format(comment_i)

    if current is not None:
        text_before = current.tail[:label_match.start()]
        text_label = current.tail[label_match.start():label_match.end()]
        text_after = current.tail[label_match.end():]
        current.tail = text_before
        current_parent.insert(current_parent.index(current)+1, anchor)
        anchor.tail = text_label
        if note_type == 'gloss':
            current_parent.insert(current_parent.index(anchor)+1, app)
            app.tail = text_after
    else:
        text_before = current_parent.text[:label_match.start()]
        text_label = current_parent.text[label_match.start():label_match.end()]
        text_after = current_parent.text[label_match.end():]

        if current_parent.tag not in ENCLOSING_TAGS:
            current_parent.text = text_before
            current_parent.insert(0, anchor)
            anchor.tail = text_label
            if note_type == 'gloss':
                current_parent.insert(current_parent.index(anchor)+1, app)
                app.tail = text_after
        else:
            if text_before:
                hi_before = ET.XML('<{} />'.format(current_parent.tag))
                hi_before.text = text_before
                hi_before.attrib.update(current_parent.attrib)
                current_parent.addprevious(hi_before)
            if text_after:
                hi_after = ET.XML('<{} />'.format(current_parent.tag))
                hi_after.text = text_after
                hi_after.attrib.update(current_parent.attrib)
                current_parent.addnext(hi_after)
            current_parent.text = text_label
            current_parent.addprevious(anchor)
            if note_type == 'gloss':
                current_parent.addnext(app)

    if note_type == 'gloss':
        note = ET.SubElement(app, 'note')
    else:
        note = ET.XML('<note />')
        anchor.addnext(note)

    note.attrib['place'] = 'bottom'
    note.attrib['type'] = note_type

    if note_type == 'gloss':
        label = ET.SubElement(note, 'label')
        label.text = label_text
        label.tail = ' ' + (note_text or '').strip()
        return anchor
    else:
        note.text = note_text
        note.tail = text_after
        return anchor

def create_dud_comment(comment_i, label_text, note_text, anchor_id_template, app_id_template):
    anchor = ET.XML('<anchor />')
    anchor.attrib[add_namespace('id', xml_namespace)] = anchor_id_template.format(comment_i)

    app = ET.XML('<app />')
    app.attrib['from'] = app_id_template.format(comment_i)

    note = ET.SubElement(app, 'note')
    note.attrib['place'] = 'bottom'
    note.attrib['type'] = 'gloss'

    label = ET.SubElement(note, 'label')
    label.text = label_text
    label.tail = note_text

    anchor_str = ET.tostring(anchor, encoding='utf-8').decode('utf-8')
    app_str = ET.tostring(app, encoding='utf-8').decode('utf-8')
    return ' '.join((anchor_str, app_str))

def add_footnotes(tei_tree, footnotes, comment_i, anchor_id_template, app_id_template):
    """Add footnotes.

    This used to be the ending part of add_comments, because comments and footnotes share numeration.
    For now, this should not work, because the format of footnotes changed.
    """
    note = None
    footnote_re = re.compile(r'<FN_(\d+)>')
    for elem in tei_tree.xpath('//text/*[self::body or self::back]/div/p'):
        footnote_match = footnote_re.search(str(elem.text))
        
        if footnote_match is not None:
            footnote_num = footnote_match.group(1)
            if footnote_num in footnotes:
                comment_i += 1
                note = add_comment(elem, footnote_match, comment_i, '', footnotes[footnote_num], anchor_id_template, app_id_template, note_type='commentary')

            if note is None and len(elem) > 0:
                note = elem[0]

            while note is not None:
                footnote_match = footnote_re.search(str(note.tail))
                if footnote_match is not None:
                    footnote_num = footnote_match.group(1)
                    if footnote_num in footnotes:
                        comment_i += 1
                        note = add_comment(elem, footnote_match, comment_i, '', footnotes[footnote_num], anchor_id_template, app_id_template, current=note, note_type='commentary')
                else:
                    break
    return tei_tree

def add_footnote(element_to_extend, last_comment_i, footnotes_text, footnote_tail, anchor_id_template, app_id_template):
    anchor = ET.SubElement(element_to_extend, 'anchor')
    anchor.attrib[add_namespace('id', xml_namespace)] = anchor_id_template.format(last_comment_i)
    note = ET.SubElement(element_to_extend, 'note')
    note.attrib['place'] = 'bottom'
    note.attrib['type'] = 'commentary'
    note.text = footnotes_text
    note.tail = footnote_tail
    return note

def add_critical_apparatus(args, tei_tree, critical, edition_page_break_numbers, pb_po_ed, doc_num):
    # we only go through pages for which we've found
    # page breaks and have critical apparatus

    if args.apparatus_file:
        apparatus_file = open(args.apparatus_file, 'w', encoding='utf-8')

    critical_failure_count = 0
    failed = {}

    active_page_break_numbers = sorted(set(edition_page_break_numbers) & set(critical))
    for pe_number in active_page_break_numbers:
        if args.show_critical_progress:
            print('Adding critical apparatus for page {}'.format(pe_number), end='\n\n', file=sys.stderr)

        # find page break
        current = tei_tree.xpath('//text/*[self::body or self::back]/div[1]/p/pb[@n="{}"]'.format(pe_number))[0]

        # find p tag containing this page break
        start_current_parent = current.getparent()
        look_in_tail = True

        # save current starting position to restart from it in case nothing was found
        saved_current = current

        # save current number to restart if the number drops below (inititally current number is None)
        prev_number = None

        for number, lem, rdg in critical[pe_number]:
            if prev_number is not None and int(number) < int(prev_number):
                saved_current = current = tei_tree.xpath('//text/*[self::body or self::back]/div[1]/p/pb[@n="{}"]'.format(pe_number))[0]
                start_current_parent = current.getparent()
                look_in_tail = True
            prev_number = number

            lem_regex = create_label_regex(lem[0][1])
            current_parent = start_current_parent
            search = True

            # look in pb.tail, anchor.tail, app.tail, p.text
            while search and current_parent is not None:
                
                if look_in_tail:
                    lem_match = lem_regex.search(strip_accents(safe(current.tail)))
                    if lem_match is not None:
                        #if args.show_critical_progress:
                        #    print('Found {} "{}" in "{}"'.format(number, lem, current.tail), end='\n\n', file=sys.stderr)

                        saved_current = current = add_critical(current_parent, lem_match, lem, rdg, pb_po_ed, doc_num, current=current)
                        break
                    else:
                        # if nothing found, go to the next pe
                        current = current.getnext()
                        if current is None:
                            current_parent = current_parent.getnext()
                            look_in_tail = False
                        elif current.tag == 'pb':
                            search = False
                else:
                    lem_match = lem_regex.search(strip_accents(safe(current_parent.text)))
                    if lem_match is not None:
                        #if args.show_critical_progress:
                        #    print('Found {} "{}" in "{}"'.format(number, lem, current_parent.text), end='\n\n', file=sys.stderr)

                        saved_current = current = add_critical(current_parent, lem_match, lem, rdg, pb_po_ed, doc_num)

                        # since we added comment in new p, change starting p tag
                        start_current_parent = current_parent
                        break
                    else:
                        # take the first child if possible
                        if len(current_parent) > 0:
                            current = current_parent[0]
                            look_in_tail = True

                            # if it's a page break, stop looking
                            if current.tag == 'pb':
                                search = False
                        # if no children, go to the next p tag
                        else:
                            current_parent = current_parent.getnext()
                
            # if this while loop ended without break, the element was not found
            else:
                # restart from the previously saved position
                current = saved_current
                current_parent = current.getparent()

                # save this entry for debug purposes
                failed.setdefault(pe_number, [])
                failed[pe_number].append((number, lem, rdg))

                critical_failure_count += 1
                if args.show_critical_progress:
                    print('{} "{}" on page {} not found'.format(number, *lem, pe_number), end='\n\n', file=sys.stderr)

                if args.apparatus_file:
                    dud_critical = create_dud_critical(lem_match, lem, rdg, pb_po_ed)
                    print('Page {}: {}'.format(pe_number, dud_critical), file=apparatus_file)

    print('Failed to place {} critical app entries'.format(critical_failure_count),
          'out of {}'.format(sum(map(len, critical.values()))), file=sys.stderr)

    if args.apparatus_file:
        apparatus_file.close()

    return tei_tree, failed

# this is a block of small utility functions for parsing
# more complicated cases of references to witnesses

def repair_ve(possible_wits, text):
    """Try and repair cases like "vynech. veW" -> "vynech. ve W" and replace "a" for comma """
    repair_re_pattern = r'\b(ve?)({})\b'.format(possible_wits)
    repaired = re.sub(repair_re_pattern, r'\1 \2', text)
    return re.sub(' +', ' ', repaired)

def get_possible_wits(doc_num):
    """Get a list of possible witnesses based on doc id"""
    wit_dict = edition_ids[doc_num]
    return sorted(wit_dict, key=len, reverse=True)

def match_wit_simple(text, possible_wits):
    """Try and find witnesses (just W, Sr, St etc.) in the provided line"""
    wit_re_pattern = r'^(.*?)(\b(?:{0})\b(?:(?:,| a) \b(?:{0})\b)*)(.*)$'.format('|'.join(possible_wits))
    return re.match(wit_re_pattern, text)

def find_wit_simple(text, doc_num):
    if text == 'poškozená sazba':
        return 'default', text
    possible_wits = get_possible_wits(doc_num)
    text = repair_ve(possible_wits, text)
    return 'parsed', match_wit_simple(text, possible_wits)

def find_wit_complicated(text, doc_num):
    marker_words = '(?:(?:celé )?vynech\.?|(?:omylem )?t[íi]št(?:ěno)?\.?|omylem|není|nečitelné|poškozená sazba)'

    possible_wits = get_possible_wits(doc_num)
    text = repair_ve(possible_wits, text)

    tbd_match = re.search(r'\[tbd_(?:[ba]): (.*?)\]', text)
    if tbd_match is not None:
        clear_split = [candidate_wit.strip('.,') for candidate_wit in tbd_match.group(1).split()]

        if all(candidate in possible_wits for candidate in clear_split):
            # this is a simple case when witnesses were separated by whitespaces instead of commas;
            # this is mostly encountered in the left part (lem)
            wit_text = ' '.join([text[:tbd_match.start()]] +\
                                [parse_wits(', '.join(clear_split), doc_num, add_default=False)] +\
                                [text[tbd_match.end():]]).strip()
            return re.sub(' +', ' ', wit_text), None, None, None

        else:
            wit_match = re.search(r' ?\[tbd(?:_[ba]): ({} ve? )({})\]'.format(marker_words, '|'.join(possible_wits)), text)
            if wit_match is not None:
                return text[:wit_match.start()], wit_match.group(1), wit_match.group(2), ''
            else:
                wit_match = re.search(r' ?\[tbd(?:_[ba]): (ve? )({}) ({})\]'.format('|'.join(possible_wits), marker_words), text)
                if wit_match is not None:
                    return text[:wit_match.start()], wit_match.group(1), wit_match.group(2), wit_match.group(3)
                else:
                    wit_match = re.search(r' ?\[tbd(?:_[ba]): ({}) (\(omylem|nezřetelné\)|viz výše)\]'.format('|'.join(possible_wits)), text)
                    if wit_match is not None:
                        return text[:wit_match.start()], '', wit_match.group(1), wit_match.group(2)
                    else:
                        reserve_wit_match = re.search(r' ?\[tbd(?:_[ba]): ({})\]'.format(marker_words), text)
                        if reserve_wit_match is not None:
                            return text[:reserve_wit_match.start()], reserve_wit_match.group(1), None, None
                        else:
                            return None, None, None, None

    return None, None, None, None

def add_critical(current_parent, lem_match, lem_text, rdg_text, pb_po_ed, doc_num, current=None):
    app = ET.XML('<app />')

    # left side
    lem = ET.SubElement(app, lem_text[0][2])
    
    if 'tbd' in lem_text[0][0]:
        wit_text, note_text, note_ref, note_text_after = find_wit_complicated(lem_text[0][0], doc_num)
        if wit_text is not None and note_text is not None:
            lem.attrib['wit'] = wit_text
            add_critical_note(note_text, note_ref, '', app, lem, doc_num)
        elif wit_text is not None and note_text is None:
            lem.attrib['wit'] = wit_text
            lem.text = lem_text[0][1]
        else:
            lem.attrib['wit'] = lem_text[0][0]
            lem.text = lem_text[0][1]
    else:
        lem.attrib['wit'] = lem_text[0][0]
    # --------------------------------

    # text before/inside/after
    matched_text = ""

    if current is not None:
        matched_text = current.tail[lem_match.start():lem_match.end()]
        text_before = current.tail[:lem_match.start()]
        text_after = current.tail[lem_match.end():]
        current.tail = text_before
        current_parent = current.getparent()
        current_parent.insert(current_parent.index(current)+1, app)
    else:
        matched_text = current_parent.text[lem_match.start():lem_match.end()]
        text_before = current_parent.text[:lem_match.start()]
        text_after = current_parent.text[lem_match.end():]
        current_parent.text = text_before
        current_parent.insert(0, app)
    
    punctuation = ".,:;?!"
    raw_lemma_label = lem_text[0][1].strip()
    
    if (matched_text and matched_text[-1] in punctuation and 
        not raw_lemma_label.endswith(matched_text[-1])):
        
        # Move last char to text_after
        text_after = matched_text[-1] + text_after
        matched_text = matched_text[:-1]

    lem.text = matched_text
    lem.tail = ' '
    # --------------------------------

    # right side
    for wit, text in rdg_text:
        rdg = ET.SubElement(app, 'rdg')

        if wit == 'tbd':
            # more complicated case, where we might need to add a note
            status, found_wit = find_wit_simple(text, doc_num)
            if status == 'default':
                rdg.attrib['wit'] = '#' + default_edition_ids[doc_num]['DJAK03']
                note = ET.SubElement(app, 'note')
                hi = ET.SubElement(note, 'hi')
                hi.attrib['rend'] = 'italic'
                hi.text = text
            else:
                if found_wit is None:
                    rdg.attrib['wit'] = 'unrecognized_italic'
                    rdg.text = text
                else:
                    before, wits, after = found_wit.groups()
                    add_critical_note(before, wits, after, app, rdg, doc_num)
        elif 'tbd' in wit:
            # even more complicated case
            wit_text, note_text, note_ref, note_text_after = find_wit_complicated(wit, doc_num)

            if wit_text is not None and note_text is not None and note_ref is not None:
                rdg.attrib['wit'] = wit_text
                if text:
                    rdg.text = text
                add_critical_note(note_text, note_ref, note_text_after, app, rdg, doc_num, place=re.search('tbd_([ab])', wit).group(1))

            elif wit_text is not None and note_text is not None and note_ref is None:
                rdg.attrib['wit'] = '#' + default_edition_ids[doc_num]['DJAK03']
                # Check if this is an editorial marker like "omylem"
                if any(marker in note_text for marker in ['omylem', 'tištěno', 'vynech']):
                    hi = ET.SubElement(rdg, 'hi')
                    hi.attrib['rend'] = 'italic'
                    hi.text = note_text
                    # Append the actual reading text after the italic marker
                    if text:
                        hi.tail = ' ' + text
                    elif note_text_after:
                        hi.tail = ' ' + note_text_after
                else:
                    # Fallback to old behavior for other notes
                    if text:
                        rdg.text = text
                    add_critical_note(note_text, note_ref, note_text_after, app, rdg, doc_num, place=re.search('tbd_([ab])', wit).group(1))

            elif wit_text is not None and note_text is None:
                rdg.attrib['wit'] = wit_text
                rdg.text = text

            else:
                rdg.attrib['wit'] = wit
                rdg.text = text

        elif wit == '':
            rdg.attrib['wit'] = '#' + default_edition_ids[doc_num]['DJAK03']
            rdg.text = text
        else:
            rdg.attrib['wit'] = wit
            rdg.text = text
    # --------------------------------

    app.tail = text_after
    return app

def add_critical_note(before, wits, after, app, rdg, doc_num, place='a'):
    if wits is not None:
        parsed_wits = parse_wits(wits, doc_num, add_default=False)
    else:
        parsed_wits = '#' + default_edition_ids[doc_num]['DJAK03']

    if 'wit' not in rdg.attrib or rdg.attrib['wit'] == '':
        rdg.attrib['wit'] = parsed_wits
    parsed_wits = parsed_wits.split()

    note = ET.XML('<note/>')
    if place == 'a':
        rdg.addnext(note)
    else:
        rdg.addprevious(note)

    hi = ET.SubElement(note, 'hi')
    hi.attrib['rend'] = 'italic'
    hi.text = before

    if wits is not None:
        delimiters = re.findall('(, | a )', wits) + [None]
        split_wits = re.split('(?:, | a )', wits)
        for i, (wit_ref, wit, delim) in enumerate(zip(parsed_wits, split_wits, delimiters)):
            ref = ET.SubElement(hi, 'ref')
            ref.attrib['target'] = wit_ref
            ref.text = wit
            if i != len(parsed_wits) - 1:
                ref.tail = delim
            else:
                ref.tail = after

def create_dud_critical(lem_match, lem_text, rdg_text, pb_po_ed):
    app = ET.XML('<app />')

    # left side
    lem = ET.SubElement(app, lem_text[0][2])
    lem.attrib['wit'] = lem_text[0][0]
    lem.text = ' '

    # right side
    for wit, text in rdg_text:
        rdg = ET.SubElement(app, 'rdg')
        rdg.attrib['wit'] = wit
        rdg.text = text

    app_str = ET.tostring(app, encoding='utf-8').decode('utf-8')

    return app_str

def check_critical_apparatus(tei_tree):
    for lem in tei_tree.xpath('//lem'):

        lem_regex = re.compile(re.escape(safe(lem.text)))
        app = lem.getparent()
        suspicious = False
        current_element = app

        while not suspicious and current_element is not None:
            if lem_regex.search(safe(current_element.tail)) is not None:
                suspicious = True
            else:
                current_element = current_element.getnext()
                if (current_element is not None
                   and current_element.tag == 'app'
                   and len(current_element) > 0
                   and current_element[0].tag == 'lem'):
                    break
        if suspicious:
            app.attrib['suspicious'] = 'yes'                    
            
    return tei_tree

def check_critical_inside_critical(tei_tree, failed_critical):
    critical_hits = 0
    anchor_hits = 0
    for pe_number in failed_critical:
        # find critical entries for this page number
        inserted_critical_list = tei_tree.xpath('//text/*[self::body or self::back]/div[1]/p/pb[@n="{}"]/../app/*[self::lem or self::rdg][1]'.format(pe_number))

        for number, lem, rdg in failed_critical[pe_number]:
            lem_regex = create_label_regex(lem[0][1])
            for inserted_critical in inserted_critical_list:
                match = lem_regex.search(inserted_critical.text)
                if match is not None:
                    critical_hits += 1

        # find anchored pieces of text to check them
        anchor_list = tei_tree.xpath('//text/*[self::body or self::back]/div[1]/p/pb[@n="{}"]/../anchor'.format(pe_number))
        for number, lem, rdg in failed_critical[pe_number]:
            lem_regex = create_label_regex(lem[0][1])
            for anchor in anchor_list:
                match = lem_regex.search(safe(anchor.tail))
                if match is not None:
                    anchor_hits += 1

    print('Found {} critical entries inside other critical entries'.format(critical_hits), file=sys.stderr)
    print('Found {} critical entries in anchors'.format(anchor_hits), file=sys.stderr)

def add_original_pb(tei_tree, pb_po_ed):
    for elem in tei_tree.iter():
        # check for original page break
        po_match = re.search(r'(.*?)(?:\| ?)?<PO(?:_(\w?\d*))?>(.*)', str(elem.tail))
        if po_match is not None:
            text_before, po_number, text_after = po_match.groups()
            elem.tail = text_before
            pb_elem = ET.XML('<pb />')
            parent = elem.getparent()
            parent.insert(parent.index(elem)+1, pb_elem)
            # sometimes, there is no number
            if po_number is not None:
                pb_elem.attrib['n'] = po_number
            pb_elem.attrib['ed'] = pb_po_ed
            pb_elem.attrib['break'] = 'no'
            pb_elem.tail = text_after

        po_match_in_text = re.search(r'(.*?)(?:\| ?)?<PO(?:_(\w?\d*))?>(.*)', str(elem.text))
        if po_match_in_text is not None:
            text_before, po_number, text_after = po_match_in_text.groups()
            pb_elem = ET.XML('<pb />')
            elem.text = text_before
            elem.insert(0, pb_elem)
            # sometimes, there is no number
            if po_number is not None:
                pb_elem.attrib['n'] = po_number
            pb_elem.attrib['ed'] = pb_po_ed
            pb_elem.attrib['break'] = 'no'
            pb_elem.tail = text_after

    return tei_tree

def add_bible_refs_note(tei_tree):
    """
    Processes refs in note tags exclusively
    """ 
    ref_template_1 = r'(?<=\()(\d )?[A-Z][a-z]+(\.)? \d+,.*?\d+(?=( etc\.)?\))'
    ref_template_2 = r'(?<=[Ss]rov\. )(\d )?[A-Z]([a-z]+)? \d+.*'
    for template in [ref_template_1, ref_template_2]:
        for elem in tei_tree.xpath('//text/*[self::body or self::back]/div[1]/p/app/note/label'):
            match = re.search(template, strip_accents(safe(elem.tail)))
            if match is not None:
                list_of_matches = elem.tail[match.start():match.end()].split('; ')
                if len(list_of_matches) == 1:
                    add_bible_ref(elem.getparent(), match.start(), match.end(), elem)
                else:
                    start_position = match.start()
                    current_elem = elem
                    parent = elem.getparent()
                    added_refs = []
                    for i, ref_text in enumerate(list_of_matches):
                        if re.search(r'(\d|n\.|\.“|aj\.\))$', ref_text) is not None:
                            current_end_position = start_position + len(ref_text)
                            current_elem = add_bible_ref(parent, start_position, current_end_position, current_elem)
                            start_position = 2
                        else:
                            current_elem.tail = '; '.join(list_of_matches[i:])
                            break
    return tei_tree

def add_bible_refs(tei_tree):
    ref_template_1 = r'(?<=\()(\d )?[A-Z][a-z. ]+?\d+(?:[,.:] ?\d+)*(?=.*?\))'
    ref_template_2 = r'(?<=\()ibid.*?\d+(?=( etc\.)?\))'

    for template in [ref_template_1, ref_template_2]:
        for elem in tei_tree.xpath('//text/*[self::body or self::back]/div[1]/p'):
            current = None
            match = re.search(template, strip_accents(safe(elem.text)))
            if match is not None:
                ref = add_bible_ref(elem, match.start(), match.end(), current)
                current = ref
            if current is None and len(elem) > 0:
                current = elem[0]
            while current is not None:
                match = re.search(template, strip_accents(safe(current.tail)))
                if match is not None:
                    ref = add_bible_ref(elem, match.start(), match.end(), current)
                    current = ref
                else:
                    current = current.getnext()

    return tei_tree

def add_bible_refs_epigraph(tei_tree):
    ref_template_3 = r'(\d )?[A-Z]([a-z]+)?.*?\.[ –-]\d+((, v)?\.[ –-]\d+)*'

    for template in [ref_template_3]:
        for elem in tei_tree.xpath('//text/front/titlePage[1]/epigraph/q'):
            current = None
            match = re.search(template, strip_accents(elem.text))
            if match is not None:
                ref = add_bible_ref(elem, match.start(), match.end(), current)
                current = ref
            if current is None and len(elem) > 0:
                current = elem[0]
            while current is not None:
                match = re.search(template, strip_accents(current.tail))
                if match is not None:
                    ref = add_bible_ref(elem, match.start(), match.end(), current)
                    current = ref
                else:
                    current = current.getnext()

    return tei_tree

def add_bible_ref(elem, match_start, match_end, current):
    """
    Adds ref tag and attrubites for one Bible ref
    """   
    ref = ET.XML('<ref />')
    ref.attrib['type'] = 'canon'
    ref.attrib['subtype'] = 'Bible'

    if current is None:
        text_before = elem.text[:match_start]
        text = elem.text[match_start:match_end]
        text_after = elem.text[match_end:]
        elem.text = text_before
        elem.insert(0, ref)
        ref.text = text
        ref.tail = text_after
    else:
        tail_before = current.tail[:match_start]
        text = current.tail[match_start:match_end]
        tail_after = current.tail[match_end:]
        current.tail = tail_before
        elem.insert(elem.index(current)+1, ref)
        ref.text = text
        ref.tail = tail_after

    return ref

def fix_first_pb(tei_tree):
    pb_elem = ET.XML('<pb />')
    pb_elem.attrib.update(tei_tree.xpath('//text/*[self::body or self::back]/div[1]/p[1]/pb[1]')[0].attrib)
    tei_tree.xpath('//text/*[self::body or self::back]/div[1]')[0].insert(0, pb_elem)
    tei_tree.xpath('//text/*[self::body or self::back]/div[1]')[0].remove(tei_tree.xpath('//text/*[self::body or self::back]/div[1]/p[1]')[0])

    return tei_tree

# the following is a block of related functions that add more or less
# simple tags, such as <hi> (custom styles), <lang> (language), 
# and <add place="margin"> (margin text)

def add_simple_tags(tei_tree, xpath, regex, add_tag_function, check_it=False):
    """Go through the tree and add simple tags

    This is a generalized function that looks for all elements in :xpath:,
    checks if text and/or tail contains a pattern specified by :regex:,
    and adds certain tag using :add_tag_function:
    """
    for elem in tei_tree.xpath(xpath):
        current = None
        match = regex.search(safe(elem.text))
        if match is not None:
            current = add_tag_function(elem, match, current, check_it)
        elif len(elem) > 0:
            current = elem[0]

        while current is not None:
            match = regex.search(safe(current.tail))
            if match is not None:
                current = add_tag_function(elem, match, current, check_it)
            else:
                current = current.getnext()

    return tei_tree    

def add_custom_styles_pre(tei_tree):
    """Wrapper function for add_simple_tags function to add <hi> tags"""
    rend_regex = re.compile(r'(.*?)<(REND_SP|REND_I)>(?:(.*?)(</\2>)|(.*))')
    tei_tree = add_simple_tags(tei_tree,
                               '//text/*[self::body or self::back]/div/*[self::p or self::head or self::bibl]',
                               rend_regex,
                               add_custom_tag,
                               check_it=False)
    return tei_tree

def add_custom_styles_post(tei_tree):
    """Wrapper function for add_simple_tags function to add <hi> tags"""
    rend_regex = re.compile(r'(.*?)<(REND_SP|REND_I)>(?:(.*?)(</\2>)|(.*))')
    tei_tree = add_simple_tags(tei_tree,
                               '//text//app/note',
                               rend_regex,
                               add_custom_tag,
                               check_it=False)
    return tei_tree

def add_custom_tag(elem, match, current, check_it=False):
    """Add hi tag and attrubites for one element"""
    opening_tag = match.group(2)

    if opening_tag == 'REND_SP':
        rend_style = 'spaced'
    elif opening_tag == 'REND_I':
        rend_style = 'italic'
    else:
        print('Unknown opening style tag: ', opening_tag, file=sys.stderr)

    closing_regex = re.compile(r'(.*?)</({})>(.*)'.format(opening_tag))

    return add_complex_tag(elem, match, current, closing_regex, opening_tag, 'hi', {'rend': rend_style}, check_it=False)

def glue_custom_styles(tei_tree):
    for element in tei_tree.xpath('//text/*[self::body or self::back]/div/p'):
        if len(element) > 1:
            prev_subelement = element[0]
            for subelement in element[1:]:
                if (prev_subelement.tag == subelement.tag == 'hi'
                   and (len(prev_subelement.tail) < 5
                   or tail_is_empty(prev_subelement))):
                    subelement.text = ''.join(map(safe, (prev_subelement.text, prev_subelement.tail, subelement.text)))
                    element.remove(prev_subelement)
                prev_subelement = subelement

    return tei_tree

def add_margins(tei_tree):
    """Wrapper function for add_simple_tags function to add <add place="margin"> tags"""
    return add_simple_tags(tei_tree,
                           '//text/*[self::body or self::back]/div/*[self::p or self::head]',
                           re.compile(r'(.*?)<(M)>(?:(.*?)(</M>)|(.*))'),
                           add_margin_tag,
                           check_it=False)

def add_margin_tag(elem, match, current, check_it=False):
    """Add <add place="margin"> tag and attrubites for one element"""
    closing_regex = re.compile(r'(.*?)</(M)>(.*)')
    return add_complex_tag(elem, match, current, closing_regex, 'M', 'add', {'place': 'margin'}, check_it=False)

def add_simple_tag(parent, match, current, tag, attribs):
    """Generalized function to add an element"""
    opening_tag = match.group(1)
    text = match.group(2)
    closing_tag = match.group(3)

    insert = ET.XML('<{} />'.format(tag))
    insert.attrib.update(attribs)
    insert.text = text

    if current is None:
        text_before = parent.text[:match.start()]
        text_after = parent.text[match.end():]
        insert_index = 0
        parent.text = text_before
    else:
        text_before = current.tail[:match.start()]
        text_after = current.tail[match.end():]
        insert_index = parent.index(current)+1
        current.tail = text_before

    if opening_tag not in text_after:
        insert.tail = re.sub(closing_tag, '', text_after)
    else:
        insert.tail = text_after
    parent.insert(insert_index, insert)

    return insert

def add_lang_elems_pre(tei_tree):
    """Wrapper function for add_simple_tags to add language elements"""
    # first, compile regex to find language tags
    lang_regex = re.compile(r'(.*?)<(LAT|GREEK|GER|CZECH)>(?:(.*?)(</\2>)|(.*))')

    # add foreign elements to p and head tags
    tei_tree = add_simple_tags(tei_tree,
                               '//text/*[self::body or self::back]/div/*[self::p or self::head]',
                               lang_regex,
                               add_lang_elem,
                               check_it=True)

    # add foreign elements to p and head tags that contain <hi> tag
    tei_tree = add_simple_tags(tei_tree,
                               '//text/*[self::body or self::back]/div/*[self::p or self::head]/hi',
                               lang_regex,
                               add_lang_elem,
                               check_it=True)

    # add foreign elements to epigraphs
    tei_tree = add_simple_tags(tei_tree,
                               '//text/front/titlePage/epigraph/q',
                               lang_regex,
                               add_lang_elem)
    return tei_tree

def add_lang_elems_post(tei_tree):
    # first, compile regex to find language tags
    lang_regex = re.compile(r'(.*?)<(LAT|GREEK|GER|CZECH)>(?:(.*?)(</\2>)|(.*))')

    # add foreign elements to note tags inside comments
    tei_tree = add_simple_tags(tei_tree,
                               '//text/*[self::body or self::back]//note',
                               lang_regex,
                               add_lang_elem)
    # add foreign elements to note tags inside comments
    tei_tree = add_simple_tags(tei_tree,
                               '//text/*[self::body or self::back]//note/label',
                               lang_regex,
                               add_lang_elem)
    return tei_tree

def add_lang_elem(elem, match, current, check_it):
    lang_tag = match.group(2)
    check_it = check_it and lang_tag != 'GREEK'
    rend_lang = {'LAT': 'la', 'GREEK': 'el', 'GER': 'de', 'CZECH': 'cs'}.get(lang_tag)
    closing_regex = re.compile(r'(.*?)</({})>(.*)'.format(lang_tag))
    return add_complex_tag(elem, match, current, closing_regex, lang_tag, 'foreign', {add_namespace('lang', xml_namespace): rend_lang}, check_it)

def add_complex_tag(parent, match, current, closing_regex, original_tag, tag, attribs, check_it):
    if current is None:
        insert_index = 0
    else:
        insert_index = parent.index(current) + 1

    insert = ET.Element(tag)
    insert.attrib.update(attribs)
    if match.group(3) is not None:
        insert.text = match.group(3)
    else:
        insert.text = match.group(5)

    # simple case: the opening and the closing text tag belong to the same element text or tail
    if match.group(4) is not None:

        if current is None:
            insert.tail = parent.text[match.end():]
            parent.text = match.group(1)
        else:
            insert.tail = current.tail[match.end():]
            current.tail = match.group(1)

        parent.insert(insert_index, insert)
        return insert

    # complicated case: we only found the opening tag in element text or tail
    # this would mean that we need to collect all the intervening tags as well
    inside_index = 0
    if current is None:
        parent.text = match.group(1)
    else:
        current.tail = match.group(1)

    for subelement in parent[insert_index:]:
        # first, check if ran into <pb>
        if subelement.tag == 'pb':

            # close the tag we were assembling, add it, start a new tag with the same attributes
            subelement.addprevious(insert)
            insert = ET.Element(tag)
            insert.attrib.update(attribs)

            tail_match = closing_regex.match(subelement.tail)
            if tail_match is not None:
                # add the second part of the tag right away and be done with it
                insert.text = tail_match.group(1)
                insert.tail = tail_match.group(3)
                subelement.tail = None
                subelement.addnext(insert)
                return insert

            insert_index = parent.index(subelement) + 1
            inside_index = 0
            if subelement.tail.strip():
                insert.text = subelement.tail
                subelement.tail = None
        else:
            insert.insert(inside_index, subelement)
            inside_index += 1

            tail_match = closing_regex.match(subelement.tail)
            if tail_match is not None:
                # add the second part of the tag right away and be done with it
                insert.tail = tail_match.group(3)
                subelement.tail = tail_match.group(1)
                parent.insert(insert_index, insert)
                return insert
    return None

def collapse_with_parent(element, allowed_parent_tags):
    parent = element.getparent()
    if (parent is not None and parent.tag in allowed_parent_tags
       and not safe(parent.text).strip() and not safe(element.tail).strip()):
        parent.tag = '_'.join((parent.tag, element.tag))
        parent.text = element.text
        parent.attrib.update(element.attrib)
        parent.remove(element)
        return parent
    return None

def collapse_nested(tei_tree):
    for hi in tei_tree.xpath('//text/*[self::body or self::back]/div//hi'):
        foreign = collapse_with_parent(hi, ['foreign'])
        if foreign is not None:
            margin = collapse_with_parent(foreign, ['add'])
        else:
            margin = collapse_with_parent(hi, ['add'])

    for foreign in tei_tree.xpath('//text/*[self::body or self::back]/div//foreign'):
        margin = collapse_with_parent(foreign, ['add'])

    return tei_tree

def expand_collapsed(tei_tree):
    for collapsed in tei_tree.xpath('//text/*[self::body or self::back]/div//add_foreign_hi'):
        foreign_hi = ET.SubElement(collapsed, 'foreign_hi')
        collapsed.tag = 'add'
        foreign_hi.text = collapsed.text
        collapsed.text = None
        for attrib in [add_namespace('lang', xml_namespace), 'rend']:
            foreign_hi.attrib[attrib] = collapsed.attrib.pop(attrib)

    for collapsed in tei_tree.xpath('//text/*[self::body or self::back]/div//foreign_hi'):
        hi = ET.SubElement(collapsed, 'hi')
        collapsed.tag = 'foreign'
        hi.text = collapsed.text
        collapsed.text = None
        hi.attrib['rend'] = collapsed.attrib.pop('rend')

    for collapsed in tei_tree.xpath('//text/*[self::body or self::back]/div//add_foreign'):
        foreign = ET.SubElement(collapsed, 'foreign')
        collapsed.tag = 'add'
        foreign.text = collapsed.text
        collapsed.text = None
        lang_attrib = add_namespace('lang', xml_namespace)
        foreign.attrib[lang_attrib] = collapsed.attrib.pop(lang_attrib)

    return tei_tree

# here ends the block of related functions that add simple tags

def add_chapter_info(tei_tree):

    for i, element in enumerate(tei_tree.xpath('//text/*[self::body or self::back]//*[self::p or self::head]')):
        if 'PREFACE' in element.text:
            div = ET.XML('<div />')
            div.attrib['type'] = 'preface'

            if 'LAT' in element.text:
                div.attrib[add_namespace('lang', xml_namespace)] = 'la'

            element.addprevious(div)

            if element.text == '':
                parent = element.getparent()
                parent.remove(element)
                position = 1
                current = div.getnext()
                while (current is not None and current.tag in ['p'] 
                       and '<CHAPTER>' not in current.text and 'PREFACE' not in current.text):
                    div.insert(position, current)
                    position += 1
                    current = div.getnext()
            else:
                div.insert(1, element)

                position = 2
                current = div.getnext()
                while (current is not None and current.tag in ['p'] 
                       and '<CHAPTER>' not in current.text and 'PREFACE' not in current.text
                       and '<TEXT_NO_HEAD>' not in current.text):
                    div.insert(position, current)
                    position += 1
                    current = div.getnext()

            element.text = re.sub(r'<PREFACE_\d(_LAT)?>', '', element.text)

        elif re.search('<CHAPTER>|ZAVÍRKA|ZÁVĚREK|MODLITBA|POŘÁDEK KAPITOL', element.text) is not None:
            element.text = element.text.replace('<CHAPTER>', '')
            if element.tag != 'head':
                element.tag = 'head'
            if element.text.isupper():
                element.attrib['rend'] = 'uppercase'

            div = ET.XML('<div />')
            div.attrib['type'] = 'chapter'
            element.addprevious(div)
            div.insert(1, element)

            position = 2
            current = div.getnext()

            while current is not None and current.tag == 'p':
                div.insert(position, current)
                position += 1
                current = div.getnext()

        elif '<TEXT_NO_HEAD>' in element.text:
            div = ET.XML('<div />')
            element.addprevious(div)
            parent = element.getparent()
            parent.remove(element)
            position = 1
            current = div.getnext()
            while current is not None and current.tag in ['p']:
                div.insert(position, current)
                position += 1
                current = div.getnext()

    return tei_tree

def add_witness(tei_tree, input_file):
    input_file_name = os.path.split(os.path.dirname(input_file))[1]
    for elem in edition_ids:
        if input_file_name.startswith(elem):
            for wit_id in edition_ids[elem]:
                witness = ET.XML('<witness />')
                witness.attrib[add_namespace('id', xml_namespace)] = edition_ids[elem][wit_id]
                witness.attrib['resp'] = '#TH'
                head = tei_tree.xpath('//teiHeader/fileDesc/sourceDesc/listWit/head')[0]
                head.addnext(witness)
    return tei_tree

def tei_template_maker():
    """
    Creates basic structure
    """
    xml = ('<TEI xml:lang="cs" xmlns:c="DJAK.xsl">'
             '<teiHeader>'
               '<fileDesc>'
                 '<titleStmt>'
                   '<title></title>'
                 '</titleStmt>'
                 '<editionStmt>'
                   '<edition>DJAK 3</edition>'
                   '<respStmt>'
                     '<resp>K vydání připravil</resp>'
                     '<name></name>'
                   '</respStmt>'
                   '<respStmt>'
                     '<resp>kódování TEI</resp>'
                     '<name>Tomáš Havelka</name>'
                   '</respStmt>'
                 '</editionStmt>'
                 '<publicationStmt>'
                   '<p><bibl>Praha</bibl></p>'
                 '</publicationStmt>'
                 '<sourceDesc>'
                   '<listWit>'
                     '<head>SIGLA</head>'
                   '</listWit>'
                 '</sourceDesc>'
               '</fileDesc>'
             '</teiHeader>'
             '<text>'
               '<front>'
                 '<titlePage>'
                   '<docTitle>'
                     '<titlePart type="main"></titlePart>'
                     '<titlePart type="desc"></titlePart>'
                   '</docTitle>'
                   '<docDate>'
                     '<date></date>'
                   '</docDate>'
                 '</titlePage>'
               '</front>'
               '<body>'
               '</body>'
             '</text>'
               '</TEI>')
    xml = bytes(xml, encoding='utf-8')
    tree = ET.parse(BytesIO(xml))
    return tree

if __name__ == "__main__":
    args = parse_arguments()
    main(args)
