import scrapy
import requests
from langdetect import detect, LangDetectException
import fitz
from transformers import pipeline
from urllib.parse import urljoin
import os
from datetime import datetime
from typing import Dict, List
from openpyxl import Workbook
from openpyxl.styles import Font
import pandas as pd
from scrapy.crawler import CrawlerProcess
import re

class ECnewsSpider(scrapy.Spider):
    name = 'ECnews11'
    base_url = 'https://health.ec.europa.eu'
    start_urls = [f'{base_url}/latest-updates_en']
    max_pages = 5  # Set maximum pages to scrape
    current_page = 1  # Track current page
    
    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'DOWNLOAD_DELAY': 0.5,
        'CONCURRENT_REQUESTS': 1,
        'DUPEFILTER_DEBUG': True
        }

            
        # Initialize Stanza pipeline for biomedical NER (drugs/chemicals)
    GITHUB_FILES = {
        "drug_interaction": "https://raw.githubusercontent.com/MariaKlap/Drug-Name-Database/refs/heads/main/drug.target.interaction.tsv",
    }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize Excel workbook
        self.drug_terms = self.load_drug_terms()
        self.wb = Workbook()
        self.ws = self.wb.active
        self.ws.title = "EC News Results"
        
        # Write headers
        headers = [
            'Title', 'Summary', 'Article URL', 'Date',
            'Document_Type', 'Product_Type', 'Countries',
            'Regions', 'Drug_names', 'Language', 'Source URL'
        ]
        self.ws.append(headers)
        
        # Make headers bold
        for cell in self.ws[1]:
            cell.font = Font(bold=True)
        
        # Track row count
        self.row_count = 1

        
        # Language code to full name mapping
        self.LANGUAGE_NAMES = {
            'af': 'Afrikaans',
            'ar': 'Arabic',
            'bg': 'Bulgarian',
            'bn': 'Bengali',
            'ca': 'Catalan',
            'cs': 'Czech',
            'cy': 'Welsh',
            'da': 'Danish',
            'de': 'German',
            'el': 'Greek',
            'en': 'English',
            'es': 'Spanish',
            'et': 'Estonian',
            'fa': 'Persian',
            'fi': 'Finnish',
            'fr': 'French',
            'gu': 'Gujarati',
            'he': 'Hebrew',
            'hi': 'Hindi',
            'hr': 'Croatian',
            'hu': 'Hungarian',
            'id': 'Indonesian',
            'it': 'Italian',
            'ja': 'Japanese',
            'kn': 'Kannada',
            'ko': 'Korean',
            'lt': 'Lithuanian',
            'lv': 'Latvian',
            'mk': 'Macedonian',
            'ml': 'Malayalam',
            'mr': 'Marathi',
            'ne': 'Nepali',
            'nl': 'Dutch',
            'no': 'Norwegian',
            'pa': 'Punjabi',
            'pl': 'Polish',
            'pt': 'Portuguese',
            'ro': 'Romanian',
            'ru': 'Russian',
            'sk': 'Slovak',
            'sl': 'Slovenian',
            'so': 'Somali',
            'sq': 'Albanian',
            'sv': 'Swedish',
            'sw': 'Swahili',
            'ta': 'Tamil',
            'te': 'Telugu',
            'th': 'Thai',
            'tl': 'Tagalog',
            'tr': 'Turkish',
            'uk': 'Ukrainian',
            'ur': 'Urdu',
            'vi': 'Vietnamese',
            'zh-cn': 'Chinese (Simplified)',
            'zh-tw': 'Chinese (Traditional)'
        }        




        # Document type classification
        self.DOCUMENT_TYPES = {
            'Announcement': ['announcement', 'notification', 'bulletin'],
            'Expert Report': ['expert report', 'technical report', 'scientific opinion'],
            'Amendment': ['amendment', 'regulation change', 'regulatory update'],
            'Law': ['law', 'legislation', 'statute', 'act'],
            'Directive': ['directive', 'guideline', 'policy'],
            'Order': ['order', 'decision', 'ruling', 'decree'],
            'Information Note': ['information note', 'information bulletin', 'notice'],
            'Q&A': ['questions and answers', 'q&a', 'faq', 'frequently asked'],
            'Instructions': ['instructions', 'manual', 'guidance', 'procedure'],
            'Resolution': ['resolution', 'conclusion', 'determination'],
            'Consultation': ['consultation', 'public hearing', 'stakeholder input'],
            'Product Info': ['product information', 'package leaflet', 'product update'],
            'Regulatory Decision': ['regulatory decision', 'approval summary', 'assessment'],
            'Evaluation': ['evaluation report', 'assessment report', 'review report'],
            'Recommendation': ['recommendation', 'advice', 'suggestion'],
            'Checklist': ['checklist', 'verification list', 'review points'],
            'Approval Tracker': ['approval tracker', 'authorization status', 'timeline'],
            'CHMP Opinion': ['chmp opinion', 'committee opinion', 'scientific opinion'],
            'Committee': ['committee', 'working group', 'task force'],
            'CV': ['curriculum vitae', 'cv', 'resume'],
            'EPAR': ['epar', 'european public assessment report'],
            'Letter': ['letter', 'correspondence', 'official communication'],
            'Meeting': ['meeting', 'conference', 'session'],
            'Withdrawal': ['withdrawn application', 'cancelled submission'],
            'Communication': ['communication', 'announcement', 'message'],
            'Decree': ['decree', 'royal decree', 'official order'],
            'Form': ['form', 'application form', 'submission form'],
            'Regulatory History': ['regulatory history', 'dossier history', 'timeline'],
            'Press Release': ['press release', 'news release', 'media statement'],
            'Ordinance': ['ordinance', 'local regulation', 'municipal law'],
            'Advisory Committee': ['advisory committee', 'committee profile'],
            'Voting': ['voting', 'committee vote', 'decision outcome'],
            'Petition': ['citizen petition', 'public petition', 'request'],
            'Federal Register': ['federal register', 'official gazette', 'journal'],
            'Inspection': ['inspection report', 'audit report', 'site visit'],
            'SOP': ['sop', 'standard procedure', 'operating protocol'],
            'BLA Approval': ['bla', 'biologics license application'],
            'BLA Supplement': ['supplemental bla', 'bla amendment'],
            'NDA Supplement': ['supplemental nda', 'nda amendment'],
            '510(k)': ['510(k)', 'premarket notification'],
            'NDA Approval': ['nda', 'new drug application'],
            'Other Type': []
        }

        # Product type classification
        self.PRODUCT_TYPES = {
            'Biological': [
                'biological', 'biologic',
                'monoclonal antibody', 'mab', 'recombinant', 'cell therapy',
                'gene therapy', 'blood product', 'plasma derived',
                'therapeutic protein', 'insulin', 'erythropoietin',
                'immunoglobulin', 'stem cell'
            ],
            'Drug Product': [
                'drug product', 'finished product', 'formulation', 'dosage form',
                'tablet', 'capsule', 'injection', 'solution', 'suspension', 'biopharmaceutical', 'biosimilar',
                'cream', 'ointment', 'gel', 'suppository', 'inhalation'
            ],
            'Drug Substance': [
                'drug substance', 'active substance', 'api', 'active ingredient',
                'bulk drug', 'chemical entity', 'reference standard'
            ],
            'Vaccine': [
                'vaccine', 'vaccination', 'immunization', 'antigen', 'adjuvant',
                'mmr', 'dtap', 'hpv', 'influenza', 'covid-19', 'sars-cov-2'
            ],
            'Small Molecule': [
                'small molecule', 'chemical drug', 'synthetic', 'organic compound',
                'nme', 'new molecular entity', 'low molecular weight'
            ],
            'Medical Device': [
                'medical device', 'implant', 'stent', 'catheter', 'prosthesis',
                'pacemaker', 'defibrillator', 'surgical instrument'
            ],
            'IVD': [
                'ivd', 'in vitro diagnostic', 'diagnostic test', 'assay',
                'reagent', 'test kit', 'analyzer', 'rapid test'
            ],
            'Other': []
        }

    # Country patterns for detection in text
    COUNTRY_PATTERNS = {
        # Europe (Complete list)
        'Albania': ['albania', 'shqipëria', 'tirana'],
        'Andorra': ['andorra', 'andorre'],
        'Austria': ['austria', 'österreich', 'vienna'],
        'Belarus': ['belarus', 'belarús', 'minsk'],
        'Belgium': ['belgium', 'belgique', 'belgie', 'brussels'],
        'Bosnia and Herzegovina': ['bosnia', 'herzegovina', 'sarajevo'],
        'Bulgaria': ['bulgaria', 'българия', 'sofia'],
        'Croatia': ['croatia', 'hrvatska', 'zagreb'],
        'Cyprus': ['cyprus', 'κύπρος', 'lefkosia'],
        'Czech Republic': ['czech republic', 'česko', 'prague'],
        'Denmark': ['denmark', 'danmark', 'copenhagen'],
        'Estonia': ['estonia', 'eesti', 'tallinn'],
        'Finland': ['finland', 'suomi', 'helsinki'],
        'France': ['france', 'french', 'paris'],
        'Germany': ['germany', 'deutschland', 'berlin'],
        'Greece': ['greece', 'ελλάδα', 'athens'],
        'Hungary': ['hungary', 'magyarország', 'budapest'],
        'Iceland': ['iceland', 'ísland', 'reykjavik'],
        'Ireland': ['ireland', 'éire', 'dublin'],
        'Italy': ['italy', 'italia', 'rome'],
        'Latvia': ['latvia', 'latvija', 'riga'],
        'Liechtenstein': ['liechtenstein', 'vaduz'],
        'Lithuania': ['lithuania', 'lietuva', 'vilnius'],
        'Luxembourg': ['luxembourg', 'luxemburg', 'luxembourg city'],
        'Malta': ['malta', 'valletta'],
        'Moldova': ['moldova', 'chișinău'],
        'Monaco': ['monaco', 'monaco-ville'],
        'Montenegro': ['montenegro', 'crna gora', 'podgorica'],
        'Netherlands': ['netherlands', 'nederland', 'holland', 'amsterdam'],
        'North Macedonia': ['north macedonia', 'macedonia', 'skopje'],
        'Norway': ['norway', 'norge', 'oslo'],
        'Poland': ['poland', 'polska', 'warsaw'],
        'Portugal': ['portugal', 'lisbon'],
        'Romania': ['romania', 'românia', 'bucharest'],
        'Russia': ['russia', 'россия', 'moscow'],
        'San Marino': ['san marino'],
        'Serbia': ['serbia', 'srbija', 'belgrade'],
        'Slovakia': ['slovakia', 'slovensko', 'bratislava'],
        'Slovenia': ['slovenia', 'slovenija', 'ljubljana'],
        'Spain': ['spain', 'españa', 'madrid'],
        'Sweden': ['sweden', 'sverige', 'stockholm'],
        'Switzerland': ['switzerland', 'suisse', 'schweiz', 'bern'],
        'Ukraine': ['ukraine', 'україна', 'kyiv'],
        'United Kingdom': ['uk', 'united kingdom', 'britain', 'london'],
        'Vatican City': ['vatican', 'holy see'],

        # Americas (Complete list)
        'Antigua and Barbuda': ['antigua', 'barbuda', "antigua and barbuda", 'saint john'],
        'Argentina': ['argentina', 'buenos aires', 'argentine republic'],
        'Bahamas': ['bahamas', 'nassau', 'commonwealth of the bahamas'],
        'Barbados': ['barbados', 'bridgetown'],
        'Belize': ['belize', 'belmopan'],
        'Bolivia': ['bolivia', 'sucre', 'la paz', 'plurinational state'],
        'Brazil': ['brazil', 'brasil', 'brasília', 'rio de janeiro', 'federative republic'],
        'Canada': ['canada', 'ottawa', 'toronto', 'ontario', 'quebec'],
        'Chile': ['chile', 'santiago', 'republic of chile'],
        'Colombia': ['colombia', 'bogotá', 'bogota', 'republic of colombia'],
        'Costa Rica': ['costa rica', 'san josé', 'san jose'],
        'Cuba': ['cuba', 'havana', 'republic of cuba'],
        'Dominica': ['dominica', 'roseau', 'commonwealth of dominica'],
        'Dominican Republic': ['dominican republic', 'santo domingo'],
        'Ecuador': ['ecuador', 'quito', 'republic of ecuador'],
        'El Salvador': ['el salvador', 'san salvador', 'republic of el salvador'],
        'Grenada': ['grenada', "saint george"],
        'Guatemala': ['guatemala', 'guatemala city', 'republic of guatemala'],
        'Guyana': ['guyana', 'georgetown', 'cooperative republic'],
        'Haiti': ['haiti', 'port-au-prince', 'republic of haiti'],
        'Honduras': ['honduras', 'tegucigalpa', 'republic of honduras'],
        'Jamaica': ['jamaica', 'kingston'],
        'Mexico': ['mexico', 'méxico', 'mexico city', 'cdmx', 'estados unidos mexicanos'],
        'Nicaragua': ['nicaragua', 'managua', 'republic of nicaragua'],
        'Panama': ['panama', 'panama city', 'republic of panama'],
        'Paraguay': ['paraguay', 'asunción', 'asunción', 'republic of paraguay'],
        'Peru': ['peru', 'lima', 'republic of peru'],
        'Saint Kitts and Nevis': ['saint kitts', 'nevis', 'basseterre'],
        'Saint Lucia': ['saint lucia', 'castries'],
        'Saint Vincent and the Grenadines': ['saint vincent', 'grenadines', 'kingstown'],
        'Suriname': ['suriname', 'paramaribo', 'republic of suriname'],
        'Trinidad and Tobago': ['trinidad', 'tobago', 'port of spain'],
        'United States': ['usa', 'u\\.s\\.', 'united states', 'america', 'washington dc', 'new york', 'california'],
        'Uruguay': ['uruguay', 'montevideo', 'oriental republic'],
        'Venezuela': ['venezuela', 'caracas', 'bolivarian republic'],

        # Asia (Complete list)
        'Afghanistan': ['afghanistan', 'kabul', 'islamic emirate'],
        'Armenia': ['armenia', 'yerevan', 'republic of armenia'],
        'Azerbaijan': ['azerbaijan', 'baku', 'republic of azerbaijan'],
        'Bahrain': ['bahrain', 'manama', 'kingdom of bahrain'],
        'Bangladesh': ['bangladesh', 'dhaka', "people's republic"],
        'Bhutan': ['bhutan', 'thimphu', 'kingdom of bhutan'],
        'Brunei': ['brunei', 'bandar seri begawan', 'darussalam'],
        'Cambodia': ['cambodia', 'phnom penh', 'kingdom of cambodia'],
        'China': ['china', 'zhongguo', 'beijing', 'shanghai', "people's republic"],
        'Cyprus': ['cyprus', 'nicosia', 'republic of cyprus'],
        'Georgia': ['georgia', 'tbilisi'],
        'India': ['india', 'bharat', 'new delhi', 'mumbai', 'republic of india'],
        'Indonesia': ['indonesia', 'jakarta', 'republic of indonesia'],
        'Iran': ['iran', 'tehran', 'islamic republic'],
        'Iraq': ['iraq', 'baghdad', 'republic of iraq'],
        'Israel': ['israel', 'jerusalem', 'state of israel'],
        'Japan': ['japan', 'nippon', 'tokyo'],
        'Jordan': ['jordan', 'amman', 'hashemite kingdom'],
        'Kazakhstan': ['kazakhstan', 'nur-sultan', 'astana', 'republic of kazakhstan'],
        'Kuwait': ['kuwait', 'kuwait city', 'state of kuwait'],
        'Kyrgyzstan': ['kyrgyzstan', 'bishkek', 'kyrgyz republic'],
        'Laos': ['laos', 'vientiane', "lao people's republic"],
        'Lebanon': ['lebanon', 'beirut', 'lebanese republic'],
        'Malaysia': ['malaysia', 'kuala lumpur', 'putrajaya'],
        'Maldives': ['maldives', 'malé', 'republic of maldives'],
        'Mongolia': ['mongolia', 'ulaanbaatar'],
        'Myanmar': ['myanmar', 'burma', 'naypyidaw', 'republic of the union'],
        'Nepal': ['nepal', 'kathmandu', 'federal democratic republic'],
        'North Korea': ['north korea', 'dprk', 'pyongyang', "democratic people's republic"],
        'Oman': ['oman', 'muscat', 'sultanate of oman'],
        'Pakistan': ['pakistan', 'islamabad', 'islamic republic'],
        'Palestine': ['palestine', 'ramallah', 'state of palestine'],
        'Philippines': ['philippines', 'manila', 'republic of the philippines'],
        'Qatar': ['qatar', 'doha', 'state of qatar'],
        'Russia': ['russia', 'russian federation', 'moscow'],
        'Saudi Arabia': ['saudi arabia', 'riyadh', 'kingdom of saudi arabia'],
        'Singapore': ['singapore', 'republic of singapore'],
        'South Korea': ['south korea', 'korea republic', 'seoul', 'republic of korea'],
        'Sri Lanka': ['sri lanka', 'colombo', 'sri jayawardenepura kotte'],
        'Syria': ['syria', 'damascus', 'syrian arab republic'],
        'Taiwan': ['taiwan', 'taipei', 'republic of china'],
        'Tajikistan': ['tajikistan', 'dushanbe', 'republic of tajikistan'],
        'Thailand': ['thailand', 'bangkok', 'kingdom of thailand'],
        'Timor-Leste': ['timor-leste', 'east timor', 'dili', 'democratic republic'],
        'Turkey': ['turkey', 'türkiye', 'ankara', 'republic of turkey'],
        'Turkmenistan': ['turkmenistan', 'ashgabat'],
        'United Arab Emirates': ['uae', 'united arab emirates', 'dubai', 'abu dhabi'],
        'Uzbekistan': ['uzbekistan', 'tashkent', 'republic of uzbekistan'],
        'Vietnam': ['vietnam', 'hanoi', 'socialist republic'],
        'Yemen': ['yemen', "sana'a", 'republic of yemen'],

        # Africa (Complete list)
        'Algeria': ['algeria', 'algiers', "people's democratic republic"],
        'Angola': ['angola', 'luanda', 'republic of angola'],
        'Benin': ['benin', 'porto-novo', 'republic of benin'],
        'Botswana': ['botswana', 'gaborone', 'republic of botswana'],
        'Burkina Faso': ['burkina faso', 'ouagadougou'],
        'Burundi': ['burundi', 'gitega', 'republic of burundi'],
        'Cameroon': ['cameroon', 'yaoundé', 'republic of cameroon'],
        'Cape Verde': ['cape verde', 'cabo verde', 'praia', 'republic of cape verde'],
        'Central African Republic': ['central african republic', 'bangui'],
        'Chad': ['chad', "n'djamena", 'republic of chad'],
        'Comoros': ['comoros', 'moroni', 'union of the comoros'],
        'Congo (Brazzaville)': ['republic of the congo', 'congo-brazzaville', 'brazzaville'],
        'Congo (Kinshasa)': ['democratic republic of the congo', 'drc', 'kinshasa'],
        "Côte d'Ivoire": ["côte d'ivoire", 'ivory coast', 'yamoussoukro'],
        'Djibouti': ['djibouti', 'republic of djibouti'],
        'Egypt': ['egypt', 'cairo', 'arab republic of egypt'],
        'Equatorial Guinea': ['equatorial guinea', 'malabo', 'republic of equatorial guinea'],
        'Eritrea': ['eritrea', 'asmara', 'state of eritrea'],
        'Eswatini': ['eswatini', 'swaziland', 'mbabane', 'kingdom of eswatini'],
        'Ethiopia': ['ethiopia', 'addis ababa', 'federal democratic republic'],
        'Gabon': ['gabon', 'libreville', 'gabonese republic'],
        'Gambia': ['gambia', 'banjul', 'republic of the gambia'],
        'Ghana': ['ghana', 'accra', 'republic of ghana'],
        'Guinea': ['guinea', 'conakry', 'republic of guinea'],
        'Guinea-Bissau': ['guinea-bissau', 'bissau', 'republic of guinea-bissau'],
        'Kenya': ['kenya', 'nairobi', 'republic of kenya'],
        'Lesotho': ['lesotho', 'maseru', 'kingdom of lesotho'],
        'Liberia': ['liberia', 'monrovia', 'republic of liberia'],
        'Libya': ['libya', 'tripoli', 'state of libya'],
        'Madagascar': ['madagascar', 'antananarivo', 'republic of madagascar'],
        'Malawi': ['malawi', 'lilongwe', 'republic of malawi'],
        'Mali': ['mali', 'bamako', 'republic of mali'],
        'Mauritania': ['mauritania', 'nouakchott', 'islamic republic'],
        'Mauritius': ['mauritius', 'port louis', 'republic of mauritius'],
        'Morocco': ['morocco', 'rabat', 'kingdom of morocco'],
        'Mozambique': ['mozambique', 'maputo', 'republic of mozambique'],
        'Namibia': ['namibia', 'windhoek', 'republic of namibia'],
        'Niger': ['niger', 'niamey', 'republic of niger'],
        'Nigeria': ['nigeria', 'abuja', 'federal republic of nigeria'],
        'Rwanda': ['rwanda', 'kigali', 'republic of rwanda'],
        'Sao Tome and Principe': ['são tomé and príncipe', 'sao tome', 'são tomé'],
        'Senegal': ['senegal', 'dakar', 'republic of senegal'],
        'Seychelles': ['seychelles', 'victoria', 'republic of seychelles'],
        'Sierra Leone': ['sierra leone', 'freetown', 'republic of sierra leone'],
        'Somalia': ['somalia', 'mogadishu', 'federal republic of somalia'],
        'South Africa': ['south africa', 'pretoria', 'cape town', 'republic of south africa'],
        'South Sudan': ['south sudan', 'juba', 'republic of south sudan'],
        'Sudan': ['sudan', 'khartoum', 'republic of the sudan'],
        'Tanzania': ['tanzania', 'dodoma', 'united republic of tanzania'],
        'Togo': ['togo', 'lomé', 'togolese republic'],
        'Tunisia': ['tunisia', 'tunis', 'republic of tunisia'],
        'Uganda': ['uganda', 'kampala', 'republic of uganda'],
        'Zambia': ['zambia', 'lusaka', 'republic of zambia'],
        'Zimbabwe': ['zimbabwe', 'harare', 'republic of zimbabwe'],

        # International/Regional
        'European Union': ['eu', 'european union', 'e\\.u\\.', 'brussels eu'],
        'African Union': ['african union', 'au', 'addis ababa'],
        'ASEAN': ['asean', 'southeast asia', 'jakarta'],
        'Global': ['who', 'world health organization', 'united nations', 'international'],
    }

    # Mapping of regions to countries
    REGION_MAPPING = {
        # Europe
        'Albania': 'Southern Europe',
        'Andorra': 'Southern Europe',
        'Austria': 'Central Europe',
        'Belarus': 'Eastern Europe',
        'Belgium': 'Western Europe',
        'Bosnia and Herzegovina': 'Southern Europe',
        'Bulgaria': 'Eastern Europe',
        'Croatia': 'Southern Europe',
        'Cyprus': 'Southern Europe',
        'Czech Republic': 'Central Europe',
        'Denmark': 'Northern Europe',
        'Estonia': 'Northern Europe',
        'Finland': 'Northern Europe',
        'France': 'Western Europe',
        'Germany': 'Central Europe',
        'Greece': 'Southern Europe',
        'Hungary': 'Central Europe',
        'Iceland': 'Northern Europe',
        'Ireland': 'Northern Europe',
        'Italy': 'Southern Europe',
        'Latvia': 'Northern Europe',
        'Liechtenstein': 'Central Europe',
        'Lithuania': 'Northern Europe',
        'Luxembourg': 'Western Europe',
        'Malta': 'Southern Europe',
        'Moldova': 'Eastern Europe',
        'Monaco': 'Western Europe',
        'Montenegro': 'Southern Europe',
        'Netherlands': 'Western Europe',
        'North Macedonia': 'Southern Europe',
        'Norway': 'Northern Europe',
        'Poland': 'Central Europe',
        'Portugal': 'Southern Europe',
        'Romania': 'Eastern Europe',
        'Russia': 'Eastern Europe',  # Transcontinental
        'San Marino': 'Southern Europe',
        'Serbia': 'Southern Europe',
        'Slovakia': 'Central Europe',
        'Slovenia': 'Southern Europe',
        'Spain': 'Southern Europe',
        'Sweden': 'Northern Europe',
        'Switzerland': 'Central Europe',
        'Ukraine': 'Eastern Europe',
        'United Kingdom': 'Northern Europe',
        'Vatican City': 'Southern Europe',

        # Americas
        # North America
        'Canada': 'North America',
        'United States': 'North America',
        'Mexico': 'North America',
        
        # Central America
        'Belize': 'Central America',
        'Costa Rica': 'Central America',
        'El Salvador': 'Central America',
        'Guatemala': 'Central America',
        'Honduras': 'Central America',
        'Nicaragua': 'Central America',
        'Panama': 'Central America',
        
        # Caribbean
        'Antigua and Barbuda': 'Caribbean',
        'Bahamas': 'Caribbean',
        'Barbados': 'Caribbean',
        'Cuba': 'Caribbean',
        'Dominica': 'Caribbean',
        'Dominican Republic': 'Caribbean',
        'Grenada': 'Caribbean',
        'Haiti': 'Caribbean',
        'Jamaica': 'Caribbean',
        'Saint Kitts and Nevis': 'Caribbean',
        'Saint Lucia': 'Caribbean',
        'Saint Vincent and the Grenadines': 'Caribbean',
        'Trinidad and Tobago': 'Caribbean',
        
        # South America
        'Argentina': 'South America',
        'Bolivia': 'South America',
        'Brazil': 'South America',
        'Chile': 'South America',
        'Colombia': 'South America',
        'Ecuador': 'South America',
        'Guyana': 'South America',
        'Paraguay': 'South America',
        'Peru': 'South America',
        'Suriname': 'South America',
        'Uruguay': 'South America',
        'Venezuela': 'South America',

        # Asia
        # Central Asia
        'Kazakhstan': 'Central Asia',
        'Kyrgyzstan': 'Central Asia',
        'Tajikistan': 'Central Asia',
        'Turkmenistan': 'Central Asia',
        'Uzbekistan': 'Central Asia',
        
        # East Asia
        'China': 'East Asia',
        'Japan': 'East Asia',
        'Mongolia': 'East Asia',
        'North Korea': 'East Asia',
        'South Korea': 'East Asia',
        'Taiwan': 'East Asia',
        
        # South Asia
        'Afghanistan': 'South Asia',
        'Bangladesh': 'South Asia',
        'Bhutan': 'South Asia',
        'India': 'South Asia',
        'Maldives': 'South Asia',
        'Nepal': 'South Asia',
        'Pakistan': 'South Asia',
        'Sri Lanka': 'South Asia',
        
        # Southeast Asia
        'Brunei': 'Southeast Asia',
        'Cambodia': 'Southeast Asia',
        'Indonesia': 'Southeast Asia',
        'Laos': 'Southeast Asia',
        'Malaysia': 'Southeast Asia',
        'Myanmar': 'Southeast Asia',
        'Philippines': 'Southeast Asia',
        'Singapore': 'Southeast Asia',
        'Thailand': 'Southeast Asia',
        'Timor-Leste': 'Southeast Asia',
        'Vietnam': 'Southeast Asia',
        
        # Middle East (West Asia)
        'Armenia': 'Middle East',
        'Azerbaijan': 'Middle East',
        'Bahrain': 'Middle East',
        'Cyprus': 'Middle East',
        'Georgia': 'Middle East',
        'Iran': 'Middle East',
        'Iraq': 'Middle East',
        'Israel': 'Middle East',
        'Jordan': 'Middle East',
        'Kuwait': 'Middle East',
        'Lebanon': 'Middle East',
        'Oman': 'Middle East',
        'Palestine': 'Middle East',
        'Qatar': 'Middle East',
        'Saudi Arabia': 'Middle East',
        'Syria': 'Middle East',
        'Turkey': 'Middle East',
        'United Arab Emirates': 'Middle East',
        'Yemen': 'Middle East',

        # ====== AFRICA ====== #
        # Northern Africa
        'Algeria': 'Northern Africa',
        'Egypt': 'Northern Africa',
        'Libya': 'Northern Africa',
        'Morocco': 'Northern Africa',
        'Sudan': 'Northern Africa',
        'Tunisia': 'Northern Africa',
        
        # Sub-Saharan Africa
        # Western Africa
        'Benin': 'Western Africa',
        'Burkina Faso': 'Western Africa',
        'Cape Verde': 'Western Africa',
        "Côte d'Ivoire": 'Western Africa',
        'Gambia': 'Western Africa',
        'Ghana': 'Western Africa',
        'Guinea': 'Western Africa',
        'Guinea-Bissau': 'Western Africa',
        'Liberia': 'Western Africa',
        'Mali': 'Western Africa',
        'Mauritania': 'Western Africa',
        'Niger': 'Western Africa',
        'Nigeria': 'Western Africa',
        'Senegal': 'Western Africa',
        'Sierra Leone': 'Western Africa',
        'Togo': 'Western Africa',
        
        # Central Africa
        'Angola': 'Central Africa',
        'Cameroon': 'Central Africa',
        'Central African Republic': 'Central Africa',
        'Chad': 'Central Africa',
        'Congo (Brazzaville)': 'Central Africa',
        'Congo (Kinshasa)': 'Central Africa',
        'Equatorial Guinea': 'Central Africa',
        'Gabon': 'Central Africa',
        'Sao Tome and Principe': 'Central Africa',
        
        # Eastern Africa
        'Burundi': 'Eastern Africa',
        'Comoros': 'Eastern Africa',
        'Djibouti': 'Eastern Africa',
        'Eritrea': 'Eastern Africa',
        'Ethiopia': 'Eastern Africa',
        'Kenya': 'Eastern Africa',
        'Madagascar': 'Eastern Africa',
        'Malawi': 'Eastern Africa',
        'Mauritius': 'Eastern Africa',
        'Mozambique': 'Eastern Africa',
        'Rwanda': 'Eastern Africa',
        'Seychelles': 'Eastern Africa',
        'Somalia': 'Eastern Africa',
        'South Sudan': 'Eastern Africa',
        'Tanzania': 'Eastern Africa',
        'Uganda': 'Eastern Africa',
        'Zambia': 'Eastern Africa',
        'Zimbabwe': 'Eastern Africa',
        
        # Southern Africa
        'Botswana': 'Southern Africa',
        'Eswatini': 'Southern Africa',
        'Lesotho': 'Southern Africa',
        'Namibia': 'Southern Africa',
        'South Africa': 'Southern Africa',

        # Oceania
        'Australia': 'Australia and New Zealand',
        'New Zealand': 'Australia and New Zealand',
        'Fiji': 'Pacific Islands',
        'Papua New Guinea': 'Pacific Islands',
        'Solomon Islands': 'Pacific Islands',
        'Vanuatu': 'Pacific Islands',

        # Special Regions
        'European Union': 'European Union',
        'African Union': 'African Union',
        'ASEAN': 'ASEAN',
        'Global': 'Global'
    }

    def get_current_page(self, url):
        from urllib.parse import urlparse, parse_qs
        query = urlparse(url).query
        page = parse_qs(query).get('page', [0])
        try:
            return int(page[0])
        except ValueError:
            return 1

    def detect_language(self, text: str) -> str:
        """Detect language and return full name (e.g., 'English')."""
        if not text.strip():
            return "Unknown"

        try:
            lang_code = detect(text)
            return self.LANGUAGE_NAMES.get(lang_code, f"Unknown ({lang_code})")
        except LangDetectException:
            return "Unknown"

    def parse(self, response):
        articles = response.css('article.ecl-content-item')
        for article in articles:
            item = {
                'Title': article.css('a.ecl-link::text').get('').strip(),
                'Article URL': article.css('a.ecl-link::attr(href)').get(),  # ← FIXED
                'Date': self.format_date(article.css('time::attr(datetime)').get(default="").strip()) 
            }
            if item['Article URL']:
                yield response.follow(
                    item['Article URL'],
                    callback=self.parse_detail_page,
                    meta={'item': item}
                )
        from urllib.parse import urlparse, parse_qs

        def get_current_page(url):
            query = urlparse(url).query
            page = parse_qs(query).get('page', [0])
            try:
                return int(page[0])
            except ValueError:
                return 1
        current_page = self.get_current_page(response.url)

        next_page_num = current_page + 1
        if next_page_num <= self.max_pages:
            next_page = f"{self.base_url}/latest-updates_en?page={next_page_num}"
            self.logger.info(f"Following to page {next_page_num}: {next_page}")
            yield response.follow(
                next_page,
                callback=self.parse,
                meta={'page': next_page_num}
                )
                     
    def format_date(self, date_str: str) -> str:
        """Convert ISO date (YYYY-MM-DD) to dd/mm/yyyy format."""
        if not date_str:
            return "Unknown"
        
        try:
            # Parse ISO date (e.g., "2025-04-03T00:00:00Z" -> "03/04/2025")
            date_obj = datetime.strptime(date_str.split('T')[0], "%Y-%m-%d")
            return date_obj.strftime("%d/%m/%Y")
        except (ValueError, IndexError):
            return "Unknown"
        
    def parse_detail_page(self, response):
        item = response.meta['item']
        
        # Add debug logging
        self.logger.info(f"Processing: {item['Title']}")
        self.logger.debug(f"Loaded {len(self.drug_terms)} drug terms")
        
        analysis_text = self.get_analysis_text(response, item.get('PDF_URL'))
        
        if analysis_text.strip():
            drug_names = self.extract_drug_names(analysis_text, item.get('Title'))
            self.logger.info(f"Found drugs in '{item['Title']}': {drug_names}")

            item['Summary'] = self.generate_summary(analysis_text)
            item['Document_Type'] = self.classify_document_type(analysis_text)
            item['Product_Type'] = self.classify_product_type(analysis_text)
        
            mentioned_countries = self.detect_mentioned_countries(analysis_text)
            item['Countries'] = ', '.join(mentioned_countries) if mentioned_countries else "None"
            item['Regions'] = ', '.join(self.detect_mentioned_regions(mentioned_countries)) if mentioned_countries else "None"

            item['Drug_names'] = ', '.join(drug_names) if drug_names else "None"
        
            item['Language'] = self.detect_language(analysis_text)

            self.logger.info(f"[MATCHED] Drugs found in '{item['Title']}': {drug_names}")

            
        else:
        # Fallback values if no text is available
            item.update({
                'Summary': "No text content available",
                'Document_Type': "Unknown",
                'Product_Type': "Unknown",
                'Countries': "None",
                'Regions': "None",
                'Drug_names': "None",
                'Language': "Unknown"
            })

    
        # Write to Excel
        self.write_to_excel(item)
        return item

    def load_drug_terms(self) -> set:
        """Load drug terms from TSV with filtering"""
        tsv_url = self.GITHUB_FILES["drug_interaction"]

        try:
            df = pd.read_csv(tsv_url, sep='\t', encoding='ISO-8859-1')
        except UnicodeDecodeError:
            df = pd.read_csv(tsv_url, sep='\t')

        columns_to_check = ['DRUG_NAME', 'GENE', 'SWISSPROT', 'ACTION_TYPE', 'TARGET_CLASS', 'TARGET_NAME']
        terms = set()

        for col in columns_to_check:
            if col in df.columns:
                col_terms = df[col].dropna().astype(str)
                col_terms = {t.strip().lower() for t in col_terms if t.strip()}
                terms.update(col_terms)

        self.logger.info(f"✅ Loaded {len(terms)} drug terms from TSV columns: {columns_to_check}")
        return terms


    def extract_drug_names(self, text: str, title: str = None) -> List[str]:
        """Improved drug name extraction with better pattern matching"""
        if not text.strip():
            return []

        matched = set()  # Avoid duplicates

        # Combine title and content for better context
        full_text = f"{title or ''} {text}".lower()

        for term in self.drug_terms:
            if len(term) < 4:
                continue  # Skip too short terms

            pattern = r'(?<!\w)' + re.escape(term.lower()) + r'(?!\w)'
            if re.search(pattern, full_text, flags=re.IGNORECASE):
                matched.add(term)

        return sorted(matched)


    def extract_text_from_pdf_preview(self, pdf_url, timeout=15):  # Remove staticmethod decorator
        """Extract text from PDF with better error handling."""
        if not pdf_url:
            return ""
            
        try:
            response = requests.get(pdf_url, timeout=timeout)
            response.raise_for_status()
            
            with fitz.open(stream=response.content, filetype="pdf") as doc:
                return " ".join(page.get_text() for page in doc[:3])  # First 3 pages
            
        except Exception as e:
            self.logger.error(f"PDF extraction failed for {pdf_url}: {str(e)}")
            return ""
     
     
    def get_analysis_text(self, response, pdf_url):
        """Extract text from either PDF or HTML content"""
        # First try to get text from the webpage
        detail_text = ' '.join(response.css('div.ecl-content-block ::text, div.ecl-editor ::text, div.ecl-u-mb-l ::text').getall()).strip()
        
        if not detail_text.strip():
            # Fallback to more generic text extraction if needed
            detail_text = ' '.join(response.css('body ::text').getall()).strip()
            
        # If PDF is available, try to extract text from it
        if pdf_url:
            try:
                pdf_text = self.extract_text_from_pdf_preview(pdf_url)
                if pdf_text.strip():  # Use PDF text if we got valid content
                    return pdf_text
            except Exception as e:
                self.logger.error(f"PDF extraction failed: {e}")
    # If we get here, either no PDF or PDF extraction failed - use webpage text
        return detail_text
    
    def write_to_excel(self, item):
        """Write the extracted item to Excel"""
        self.ws.append([
            item.get('Title'),
            item.get('Summary'),
            item.get('Article URL'),  
            item.get('Date'),
            item.get('Document_Type'),
            item.get('Product_Type'),
            item.get('Countries') or "None",
            item.get('Regions') or "None",
            item.get('Drug_names') or "None",
            item.get('Language') or "Unknown",
            self.base_url  # Source URL
        ])

        
        self.row_count += 1
     
    def extract_text_from_pdf_preview(pdf_url, timeout=15):
        """Extract text from first page of PDF with timeout"""
        if not pdf_url:
            return ""
        try:
            # Ensure we have an absolute URL
            if not pdf_url.startswith(('http://', 'https://')):
                pdf_url = urljoin('https://health.ec.europa.eu', pdf_url)
            
        # Stream the PDF with timeout
            response = requests.get(pdf_url, timeout=timeout, stream=True)
            response.raise_for_status()
        
        # Use in-memory file instead of writing to disk
            with fitz.open(stream=response.content, filetype="pdf") as doc:
                if len(doc) > 0:
                    return doc[0].get_text()
                return ""
        except Exception as e:
            print(f"PDF extraction error: {e}")
            return ""

    def generate_summary(self, text, max_length=60, min_length=40):
        if not text.strip():
            return "No text available"
    
    # Clean and truncate text to avoid token limit issues
        clean_text = ' '.join(text.split()[:800])  # Reduced from 2000 to 800 words
    
        if len(text.split()) < 50:
            return clean_text[:200] + "..."
    
        try: 
            summary = self.summarizer(clean_text, 
                                max_length=max_length, 
                                min_length=min_length,
                                truncation=True)  # Added truncation
            return summary[0]['summary_text']
        except Exception as e:
            self.logger.error(f"Summarization error: {e}")
            return clean_text[:200] + "..."

    def classify_document_type(self, text: str) -> str:
        """Classify the document type based on text content."""
        text_lower = text.lower()
        for doc_type, keywords in self.DOCUMENT_TYPES.items():
            if any(keyword in text_lower for keyword in keywords):
                return doc_type
        return "Other Type"

    def classify_product_type(self, text: str) -> str:
        """Classify the product type based on text content."""
        text_lower = text.lower()
        for product_type, keywords in self.PRODUCT_TYPES.items():
            if any(keyword in text_lower for keyword in keywords):
                return product_type
        return "Other"


    def detect_mentioned_countries(self, text: str) -> List[str]:
        """Detect all countries mentioned in the text."""
        text_lower = text.lower()
        mentioned_countries = []
        
        for country, patterns in self.COUNTRY_PATTERNS.items():
            if any(pattern in text_lower for pattern in patterns):
                mentioned_countries.append(country)
        
        return mentioned_countries

    def detect_mentioned_regions(self, countries: List[str]) -> List[str]:
        """Convert list of countries to their corresponding regions."""
        regions = set()
        for country in countries:
            if country in self.REGION_MAPPING:
                regions.add(self.REGION_MAPPING[country])
        return list(regions)

    
    def closed(self, reason):
        if hasattr(self, 'summarizer'):
            del self.summarizer
        if hasattr(self, 'wb'):
            filename = 'ec_news_results.xlsx'
            self.wb.save(filename)
            self.logger.info(f"Saved results to {filename}")

if __name__ == "__main__":
    process = CrawlerProcess()
    process.crawl(ECnewsSpider)
    process.start()

