'''
Original script from https://gist.github.com/leejeannes/5555a6559528487bfe77321d5bbceaa1?fbclid=IwAR1G7pr65k9kYM2WLV4tehzi6xjxk8riWAxMYxyEhS495O0pLl0rnppHBqM
Original author: Jeanne Lee (@leejeannes)

Modifications made by Raymond Chang (@raymond-cj-chang)
'''

from bs4 import BeautifulSoup
import requests
import csv
import pdb
import datetime
from re import sub
from decimal import Decimal
from urllib.parse import urlparse

AVALON_URL = 'https://www.avaloncommunities.com/california/san-francisco-apartments/avalon-at-mission-bay/apartments'
HEADERS = [
    'Unit Name', 
    'Unit Type', 
    'Num Bath', 
    'Sq Footage', 
    'Finish Package', 
    'Phase',
    'Floor',
    'Location',
    'Mo. Price', 
    'Effective Mo. Price', 
    'Lease Period', 
    'Lease Start 1', 
    'Lease Start 2', 
    'Image URL'
]

CODE_TO_PHASE_NAME_MAP = {
    'CA067': 'Phase 1',
    'CA800': 'Phase 2',
    'CA084': 'Phase 3',
}

FACING_BERRY_ST = set(['1', '2', '3', '4', '5', '6', '7', '8', '9'])
FACING_COURTYARD_ON_KING_ST = set(['15', '17', '21', '23', '25', '27', '29'])
FACING_COURTYARD_NEXT_TO_PHASE_2 = set(['32', '34', '36'])
FACING_PHASE_2 = set(['31', '33', '35', '37', '38'])
FACING_KING_ST = set(['10', '16', '20', '22', '24', '26', '28', '30'])

IMG_URL_PREFIX = 'https://resource.avalonbay.com/floorplans/'

def build_apartments_csv():
    page = requests.get(AVALON_URL)
    parsed_page = BeautifulSoup(page.content, 'html.parser')
    current_date_str = datetime.datetime.now().strftime('%Y%m%d')

    with open(f'avalon_mb_apartments_{current_date_str}.csv', 'w') as csv_file:
        writer = csv.writer(csv_file, delimiter=',')
        writer.writerow(HEADERS)

        apartment_cards = parsed_page.findAll('ul', {'class': 'apartment-cards'})[0]
        apartments = apartment_cards.findAll('li', {'class': 'apartment-card'})

        for index, apartment_card in enumerate(apartments):

            img_url = get_img_url(apartment_card)

            phase_code = img_url.replace(IMG_URL_PREFIX, '').split('/')[0]
            phase_name = CODE_TO_PHASE_NAME_MAP.get(phase_code)
            
            content_div = apartment_card.find('div', {'class': 'content'})
            finish_package = content_div.find('div', {'class': 'signature-collection-tag'}).text
            finish_package = finish_package.replace('Finish Package', '').strip()
            
            apartment_id = content_div.find('div', {'class':'brand-main-text-color'}).text
            apartment_id = apartment_id.replace('Apartment', '').strip()

            floor, location = get_apartment_floor_and_location(apartment_id, phase_name)
            
            details = content_div.find('div', {'class': 'details'}).text
            detail_elements = list(map(lambda x: x.strip(), details.split('•')))
            apartment_type, num_bedrooms, sqft = detail_elements[0:3]

            price_info = get_price_info(content_div)

            writer.writerow(
                [
                    apartment_id,
                    apartment_type,
                    num_bedrooms,
                    sqft,
                    finish_package,
                    phase_name,
                    floor, 
                    location,
                    price_info['monthly_price'],
                    price_info['effective_mo_price'],
                    price_info['lease_period'],
                    price_info['lease_movein_start'],
                    price_info['lease_movein_end'],
                    img_url
                ]
            )

def get_apartment_floor_and_location(apartment_id, phase_name):
    location = ''
    apartment_number = apartment_id.split('-')[1]
    if len(apartment_number) == 3:
        floor = apartment_number[0:1]
        location_code = apartment_number[1:]
    else:
        floor = apartment_number[0:2]
        location_code = apartment_number[2:]

    # this was added b/c I want to avoid moving to an apartment facing the caltrain :)
    if phase_name == 'Phase 3':
        if location_code in FACING_BERRY_ST:
            location = 'Facing Berry St'
        elif location_code in FACING_COURTYARD_ON_KING_ST:
            location = 'Facing courtyard on King St'
        elif location_code in FACING_COURTYARD_NEXT_TO_PHASE_2:
            location = 'Facing courtyard next to Phase 2'
        elif location_code in FACING_PHASE_2:
            location = 'Facing Phase 2 - probably avoid'
        elif location_code in FACING_KING_ST:
            location = 'Facing King St - AVOID!!!'
        else:
            location = '???'
    return floor, location


def get_img_url(apartment_element):
    img_tag = apartment_element.a.ul.li.img
    img_url = img_tag['data-src']

    url_parse_result = urlparse(img_url)
    # Make the image larger for easier viewing
    url_parse_result = url_parse_result._replace(query="width=1000&height=1000")

    return url_parse_result.geturl()

def get_price_info(content_element):
    price_element = content_element.find('div', {'class': 'price'})

    # Grab the last monthly price element since there may be a sale
    monthly_price_elements = price_element.findAll('span', {'class': 'brand-main-text-color'})
    monthly_price = monthly_price_elements[-1].text

    lease_period = price_element.text.split(" ")[-2]
    lease_period = lease_period.replace('mo', '')

    lease_start = content_element.find('div', {'class': 'availability'}).text
    availability_strings = lease_start.replace('Available', '').strip().split('—')
    stripped_availability_strings =list(map(lambda x: x.strip(), availability_strings))
    lease_movein_start, lease_movein_end = stripped_availability_strings[0:2]

    lease_movein_datetime = datetime.datetime.strptime(lease_movein_end + " 2020", '%b %d %Y')
    effective_mo_price = compute_effective_mo_price(monthly_price, lease_movein_datetime, lease_period)

    return {
        'lease_period': lease_period,
        'lease_movein_start': lease_movein_start,
        'lease_movein_end': lease_movein_end,
        'monthly_price': monthly_price,
        'effective_mo_price': effective_mo_price
    }

def compute_effective_mo_price(monthly_price, lease_movein_datetime, num_mo_in_lease):
    current_lease_end_datetime = datetime.datetime(2020, 7, 2)
    day_diff = (current_lease_end_datetime - lease_movein_datetime).days

    monthly_price = float(Decimal(sub(r'[^\d.]', '', monthly_price)))
    daily_price = monthly_price / 30

    # one month free
    one_month_free_discount = monthly_price / float(num_mo_in_lease)

    return (day_diff * daily_price / float(num_mo_in_lease)) + monthly_price - one_month_free_discount 

# Run
build_apartments_csv()