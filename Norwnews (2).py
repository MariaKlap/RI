from selenium import webdriver
from deep_translator import GoogleTranslator
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import scrapy
import re
import pandas as pd
from collections import Counter
from datetime import datetime
from urllib.parse import urljoin
import os
import time
from typing import List
from langdetect import detect, DetectorFactory, LangDetectException
DetectorFactory.seed = 0 


class Norwnews:
    def __init__(self, output_file='Norwnews.xlsx'):
        self.output_file = output_file
        self.data_rows = []
        self.translator = GoogleTranslator(source='auto', target='en')

        # ✅ LOAD drug terms from .tsv file
        tsv_path = 'https://raw.githubusercontent.com/MariaKlap/Drug-Name-Database/refs/heads/main/drug.target.interaction.tsv'  
        

        try:
            df = pd.read_csv(tsv_path, sep='\t')
        except UnicodeDecodeError:
            df = pd.read_csv(tsv_path, sep='\t', encoding='ISO-8859-1')
        print(f"📊 DRUG_NAME column row count (including duplicates and empty): {len(df['DRUG_NAME'])}")

        # Limit to specific columns only
        allowed_columns = {'DRUG_NAME', 'SWISSPROT', 'ACTION_TYPE', 'TARGET_CLASS', 'TARGET_NAME'}
        allowed_columns = [col for col in df.columns if col in allowed_columns]

        terms = set()
        for col in allowed_columns:
            col_terms = df[col].dropna().astype(str)
            col_terms = {t.strip().lower() for t in col_terms if len(t.strip()) > 3}
            terms.update(col_terms)

        self.drug_terms_set = terms
        print(f"✅ Loaded {len(self.drug_terms_set)} drug terms from TSV columns: {', '.join(allowed_columns)}")

                # Chrome-specific configuration
        chrome_options = Options()
        prefs = {
            "profile.default_content_settings.popups": 0,
            "profile.content_settings.exceptions.automatic_downloads.*.setting": 1,
            "profile.default_content_setting_values.automatic_downloads": 1,
            "profile.default_content_setting_values.popups": 0
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        # Use ChromeDriverManager for automatic driver management
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)



    def detect_language_name(self, text):
        try:
            lang_code = detect(text)
            return self.LANGUAGE_NAMES.get(lang_code, f"Unknown ({lang_code})")
        except LangDetectException:
            return "Unknown"

    def closed(self, reason):
        df = pd.DataFrame(self.data_rows, columns=[
            'Title',
            'Summary',
            'Article URL',
            'Date',
            'Document_Type',
            'Product_Type',
            'Countries',
            'Regions',
            'Drug_names',
            'Language',
            'Source URL'
        ])

        df.to_excel(self.output_file, index=False)
        print(f"Data saved to {self.output_file}")
        
        # Language code to full name mapping
    LANGUAGE_NAMES = {
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
    DOCUMENT_TYPES = {
        'Announcement': ['announcement', 'notification', 'bulletin'],
        'Expert Report': ['expert report', 'technical report', 'scientific opinion'],
        'Amendment': ['amendment', 'regulation change', 'regulatory update'],
        'Law': ['law', 'legislation', 'statute'],
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
        'NDA Approval': ['new drug application'],
        'Other Type': []
    }

    # Product type classification
    PRODUCT_TYPES = {
        'Biological': [
            'biological', 'biologic', 'monoclonal antibody', 'mab', 'recombinant',
            'cell therapy', 'gene therapy', 'blood product', 'plasma derived'
        ],
        'Drug Product': [
            'drug product', 'finished product', 'formulation', 'dosage form',
            'tablet', 'capsule', 'injection', 'solution'
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

    def extract_drug_names(self, text: str) -> List[str]:
        if not text.strip():
            return []

        matched = []
        for term in self.drug_terms_set:
            # Escape regex special chars and match as whole word/phrase
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, text, flags=re.IGNORECASE):
                matched.append(term)
        return matched
    

    def translate_to_english(self, text):
        """More robust translation handling"""
        if not text.strip():
            return text
        
        try:
            # Split long text to avoid API limits
            if len(text) > 5000:
                parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
                translated_parts = []
                for part in parts:
                    translated = self.translator.translate(part)
                    translated_parts.append(translated)
                    time.sleep(0.5)  # Rate limiting
                return ' '.join(translated_parts)
            return self.translator.translate(text)
        except Exception as e:
            print(f"Translation error: {str(e)}")
            return text
        
    def start_requests(self):
        base_url = 'https://www.dmp.no/nyheter'
        max_pages = 3  # Maximum number of pages to scrape
        
        try:
            self.driver.get(base_url)
            time.sleep(3)  # Initial page load
            
            # Handle consent popup if it exists
            try:
                consent_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Accept') or contains(., 'Godta')]"))
                )
                consent_button.click()
                print("Consent button clicked.")
                time.sleep(1)
            except:
                print("No consent popup found or already accepted.")
            
            current_page = 1
            
            while current_page <= max_pages:
                print(f"Processing page {current_page}")
                
                # Wait for articles to load
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, '//li[@class="list-result-wrapper"]'))
                )
                
                articles = self.driver.find_elements(By.XPATH, '//li[@class="list-result-wrapper"]')
                print(f"Found {len(articles)} articles on page {current_page}")
                
                # Debug: Print first article title to verify uniqueness
                if articles:
                    try:
                        first_title = articles[0].find_element(By.XPATH, './/h3').text
                        print(f"First article title on page {current_page}: {first_title}")
                    except Exception as e:
                        print(f"Error getting first title: {str(e)}")
                
                # Process articles
                for article in articles:
                    try:
                        # Extract elements
                        title_elem = article.find_element(By.XPATH, './/h3[@class="list-result-element-link"]')
                        title = title_elem.get_attribute('aria-label').strip() if title_elem.get_attribute('aria-label') else title_elem.text.strip()
                        
                        summary_elem = article.find_element(By.XPATH, './/p[not(parent::div[@class="element-dates"])]')
                        summary = summary_elem.get_attribute('aria-label').strip() if summary_elem.get_attribute('aria-label') else summary_elem.text.strip()
                        
                        # Translate with error handling
                        try:
                            title_en = self.translate_to_english(title)
                        except:
                            title_en = title
                            
                        try:
                            summary_en = self.translate_to_english(summary).strip().strip(',')
                        except:
                            summary_en = summary
                            
                        # Use translated text for analysis
                        combined_text = f"{title_en} {summary_en}".lower()
                        doc_type = self.classify_document(combined_text)
                        product_type = self.classify_product(combined_text)
                        countries = self.detect_countries(combined_text)
                        regions = [self.REGION_MAPPING.get(c, 'Other') for c in countries]
                        drug_names = self.extract_drug_names(combined_text)
                        
                        # Extract date
                        try:
                            date_elem = article.find_element(By.XPATH, './/time')
                            date_str = date_elem.get_attribute('datetime') or date_elem.text.strip()
                        except:
                            try:
                                date_elem = article.find_element(By.XPATH, './/div[@class="element-dates"]//p')
                                date_str = date_elem.text.replace('Publisert:', '').strip()
                            except:
                                date_str = ""
                                
                        try:
                            link = title_elem.find_element(By.XPATH, './ancestor::a').get_attribute('href')
                        except:
                            link = None
                            
                        # Create and append row data
                        language = self.detect_language_name(summary)

                        row_data = [
                            title_en,
                            summary_en,
                            link,
                            self._format_date(date_str),
                            doc_type,
                            product_type,
                            ', '.join(set(countries)) if countries else "None",
                            ', '.join(set(regions)) if regions else "None",
                            ', '.join(drug_names) if drug_names else "None",
                            language,
                            self.driver.current_url  # Store current page URL
                        ]
                        
                        self.data_rows.append(row_data)
                        print(f"Processed article: {title}")
                        
                    except Exception as e:
                        print(f"Error collecting article info: {e}")
                        continue
                
                # Break if we've reached the max pages
                if current_page >= max_pages:
                    break
                    
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight - 1000);")
                time.sleep(1.5)

                try:
                    next_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[@id='next-button' and @aria-label='Neste side']"))
                    )
                    next_button.click()
                    current_page += 1
                    time.sleep(3)
                except Exception as e:
                    print(f"No next page or button not clickable: {e}")
                    break
            self.closed('finished')
            
        except Exception as e:
            print(f"Error during scraping: {e}")
            self.closed('error')
        finally:
            if hasattr(self, 'driver') and self.driver:
                pass
            
    def generate_summary(self, text, word_limit=40):
        """Generate concise summary from full text"""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        summary = []
        word_count = 0
        
        for sentence in sentences:
            words = sentence.split()
            if word_count + len(words) <= word_limit:
                summary.append(sentence)
                word_count += len(words)
            else:
                remaining = word_limit - word_count
                if remaining >= 3:  # Only add if we can add meaningful content
                    summary.append(' '.join(words[:remaining]) + '...')
                break
            
        return ' '.join(summary)
    
    def _format_date(self, date_str):
        try:
            # Try ISO format first (from datetime attribute)
            return datetime.strptime(date_str.strip(), '%Y-%m-%d').strftime('%d/%m/%Y')
        except:
            try:
                # Try day.month.year format (Norwegian style)
                date_str = date_str.strip()
                if '.' in date_str:
                    day, month, year = date_str.split('.')
                    return f"{day.zfill(2)}-{month.zfill(2)}-{year}"
                return datetime.strptime(date_str.strip(), '%d.%m.%Y').strftime('%d/%m/%Y')
            except:
                try:
                    # Try with textual month
                    date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
                    date_obj = datetime.strptime(date_str.strip(), '%d %B %Y')
                    return date_obj.strftime('%d/%m/%Y')
                except:
                    return date_str  # Return original if all parsing fails   

    def detect_languages(self, text):
        """Detect document language with focus on accuracy"""
        lang_phrases = {
            'english': ['in english', 'english version', 'original in english'],
            'multilingual': ['available in', 'translated version', 'languages:']
            }
        
        text_lower = text.lower()
        for phrase in lang_phrases['multilingual']:
            if phrase in text_lower:
                return ['Multiple']  
            
            for phrase in lang_phrases['english']:
                if phrase in text_lower:
                    return ['English']
                return ['English']
    
    def detect_countries(self, text):
        """Detect countries/regions mentioned in text"""
        detected = []
        text = text.lower()
        for country, patterns in self.COUNTRY_PATTERNS.items():
            if any(re.search(r'\b' + pattern + r'\b', text) for pattern in patterns):
                detected.append(country)
        return detected if detected else ['Global']

    def classify_document(self, text):
        """Classify document based on keywords"""
        text = text.lower()
        for doc_type, keywords in self.DOCUMENT_TYPES.items():
            if any(keyword in text for keyword in keywords):
                return doc_type
        return 'Other Type'

    def classify_product(self, text):
        """Classify product based on keywords"""
        text = text.lower()
        for product_type, keywords in self.PRODUCT_TYPES.items():
            if any(keyword in text for keyword in keywords):
                return product_type
        return 'Other'

if __name__ == "__main__":
    scraper = Norwnews(output_file='Norwnews.xlsx')
    scraper.start_requests()
