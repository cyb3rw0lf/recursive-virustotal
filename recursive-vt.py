import yaml
import json
import hashlib
import glob
import os
import time
from virus_total_apis import PublicApi as VirusTotalPublicApi

class simpleFile:
    # simple file object, automatically calculates hash of itself

    def calculate_hash(self, file_name):
        sha256_hash = hashlib.sha256()
        with open(file_name,'rb') as f:
            # Read and update hash string value in blocks of 4K to avoid buffer overflow
            for byte_block in iter(lambda: f.read(4096),b""):
                    sha256_hash.update(byte_block)

        return(sha256_hash.hexdigest())
    
    def __init__(self, file_name):
        self.file_name = file_name
        self.hash = self.calculate_hash(file_name)

    def get_hash(self):
        return(self.hash)

    def get_file_name(self):
        return(self.file_name)

class observedEntity:
    # Contains one hash and all file names that share this hash
    # It also holds the raw VirusTotal result and provides distilled threat intel information
    def __init__(self, file):
        self.files = []
        self.files.append(file.get_file_name())
        self.hash = file.get_hash()
        self.isMalicious = False
        self.vt_result = ''
        self.positives = 0
        self.total_scanners = 1 # to avoid division by zero error

    def add_file_name(self, file_name):
        # if a file has the identical hash like another observed entity, we just add the file name
        # so that we will poll the VirusTotal result only once.
        self.files.append(file_name)

    def get_file_names(self):
        # returns the array of file names that share the hash and therefore the VirusTotal results.
        return(self.files)

    def get_hash(self):
        # returns the hash of the observed entity, also used for checking against VirusTotal
        return(self.hash)

    def add_virustotal_result(self, result):
        self.vt_result = result

         # Convert json to dictionary:
        json_data = json.loads(json.dumps(result))
        if json_data['results']['response_code'] == 1:
            # we got a valid response
            self.total_scanners = json_data['results']['total']
            self.positives = json_data['results']['positives']
            self.scan_date = json_data['results']['scan_date']

    def get_virustotal_result(self):
        return(self.vt_result)

    def is_malicious(self):
        # the definition of "malicious" is not fixed.
        # What we say here is that if a certain number of engines discover the file to be malicious,
        # then we deem it potentially malicious.
        # We use a ratio here, namely 10%:
        print(self.count_alerting_scanners() / self.count_total_scanners())
        return(self.count_alerting_scanners() / self.count_total_scanners() >= 0.1)

    def count_total_scanners(self):
        # number of AV scanners that were used to check this file
        return(self.total_scanners)

    def count_alerting_scanners(self):
        # number of AV scanners that reported the file as malicious
        return(self.positives)

    

class entityHandler:
    # manages observed entities, i.e. adds new entities if they were not observed before
    # or otherwise updates information on previously observed entities

    def __init__(self):
        self.hash_dict = {}

    def add_file(self, file):
        # check if other files with same hash were already processed (duplicates)
        new_file = simpleFile(file)
        existing_duplicates = self.hash_dict.get(new_file.get_hash())
        if existing_duplicates is not None:
            # Other files with an identical hash are already present, we just add the file name:
            existing_duplicates.add_file_name(new_file.get_file_name())
        else:
            # We see this hash for the first time and add it to the list:
            self.hash_dict.update({new_file.get_hash():observedEntity(new_file)})

    def get_entities(self):
        # returns an iterable of all observed entities so that they can be checked
        return(self.hash_dict.items())

    def count_entities(self):
        # number of entities (i.e. files with unique hash) in scope
        return(len(self.hash_dict))

    def retrieve_virustotal_results(self):
        # Starts the polling of VirusTotal results for all observed entities
        # VT rate limit is 4 requests per minute. If we have <= 4 unique hashes,
        # we can query them without waiting:
        if entity_handler.count_entities() <= 4:
            waiting_time = 0
        else:
            waiting_time = 15

        for hash, observed_entity in self.get_entities():
            observed_entity.add_virustotal_result(vt.get_file_report(hash))
            time.sleep(waiting_time)

    
# Initialize program / load config
CONFIG_FILE = 'config.yaml'

with open(CONFIG_FILE, 'r') as config_file:
    config = yaml.load(config_file)
    
VT_KEY = config['virustotal']['api_key']
FILE_PATH = config['file_path']

vt = VirusTotalPublicApi(VT_KEY)

entity_handler = entityHandler()


# recursively read all files from the given directory
for file in glob.iglob(FILE_PATH+'/**/*', recursive=True):
    # only calculate the hash of a file, not of folders:
    if os.path.isfile(file):   
        entity_handler.add_file(file)
       

# VirusTotal polling
entity_handler.retrieve_virustotal_results()

# return relevant results
for hash, observed_entity in entity_handler.get_entities():
    #print(f'Hash {hash} for the following files: {observed_entity.get_file_names()}')
    if observed_entity.is_malicious():
        print(f'Potentially malicious hash {hash} for the following files: {observed_entity.get_file_names()}')
        print(f'{observed_entity.count_alerting_scanners()} identified this file as malicious.')
        print(f'VT Result is: {observed_entity.get_virustotal_result()}')
    else:
        print(f'{observed_entity.get_file_names()} not recognized as malicious')
        print(f'VT Result is: {observed_entity.get_virustotal_result()}')

        