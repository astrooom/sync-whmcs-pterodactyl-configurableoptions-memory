"""
 Sync memory from the server in Pterodactyl Panel to the service's configurable option in WHMCS.
"""

import os
import requests
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

load_dotenv()

# WHMCS Database Configuration
CONFIGOPTION_ID = 1  # Config option ID for server memory

# Pterodactyl API Configuration
PTERO_API_KEY = os.environ.get('PTERO_API_KEY')
PTERO_PANEL_URL = os.environ.get('PTERO_URL')

WHMCS_PTERODACTYL_SERVER_ID = int(os.environ.get('PTERODACTYL_WHMCS_SERVER_ID'))

PTERODACYL_API_PER_PAGE = 99999999999999

def connect_to_database():
    try:
        connection = mysql.connector.connect(
            host=os.environ.get('DB_HOST'),
            database=os.environ.get('DB_NAME'),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD')
        )
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None
      
def get_whmcs_service_ids(connection):
    """ Fetch all pterodactyl service IDs from WHMCS. """
    cursor = connection.cursor()
    cursor.execute(f"SELECT id FROM tblhosting WHERE domainstatus = 'Active' AND server = {WHMCS_PTERODACTYL_SERVER_ID}")
    services = cursor.fetchall()
    return [service[0] for service in services]


def get_servers_memory(external_ids = []):
    """ Fetch servers and their assigned memory from Pterodactyl Panel. """
    headers = {
        'Authorization': f'Bearer {PTERO_API_KEY}',
        'Accept': 'application/json',
    }
    response = requests.get(f'{PTERO_PANEL_URL}/api/application/servers?per_page={PTERODACYL_API_PER_PAGE}', headers=headers)
    servers = response.json()['data']
    
    memory_info = {}
    for server in servers:
        external_id = server['attributes']['external_id']
        if external_id and external_id.isnumeric():
            external_id = int(external_id)
        if external_id in external_ids: # Grab only servers with matching external ID from WHMCS.
            memory_info[server['attributes']['external_id']] = int(server['attributes']['limits']['memory'])
    return memory_info

def update_whmcs_service_config(connection, server_memory):
    """ Update the WHMCS service configurations in tblhostingconfigoptions table. """
        
    cursor = connection.cursor()

    for service_id, memory in server_memory.items():

        formatted_memory_option = format_memory_option(memory)
        print(f"Updating WHMCS service config for service {service_id} with {formatted_memory_option}.")
        
        cursor.execute("""
            SELECT id FROM tblproductconfigoptionssub
            WHERE configid = %s AND optionname = %s
            """, (CONFIGOPTION_ID, formatted_memory_option))
        results = cursor.fetchone()
        option_id = results[0] if results else None

        if option_id:
            print(f"Found option ID {option_id} for {memory} linked to service {service_id}.")
            
            # Update existing service configurations
            cursor.execute("""
            UPDATE tblhostingconfigoptions
            SET optionid = %s, qty = 1
            WHERE configid = %s AND relid = %s
            """, (option_id, CONFIGOPTION_ID, service_id))
            
            print(f"Updated WHMCS service config for service {service_id} with {memory}MB memory.")
        else:
            print(f"No option ID found for {memory} linked to service {service_id}; skipping update.")


def format_memory_option(memory_mb):
    """ Format memory in MB to match WHMCS option name format '2048|2GB'. """
    gb = memory_mb / 1024
    return f"{memory_mb}|{int(gb)}GB" if gb.is_integer() else f"{memory_mb}|{gb:.1f}GB"

if __name__ == "__main__":
    connection = connect_to_database()
    if connection and connection.is_connected():
        try:
            connection.start_transaction()
            service_ids = get_whmcs_service_ids(connection)
            server_memory = get_servers_memory(service_ids)
            update_whmcs_service_config(connection, server_memory)
            
            connection.commit()
            print("Memory configuration updated successfully.")
            
        except Exception as e:
            connection.rollback()
            print(f"An error occurred: {e}")
        
        connection.close()
