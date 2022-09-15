# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/01_download.ipynb (unless otherwise specified).

__all__ = ['Ladsweb', 'read_log', 'update_log', 'order_status', 'download_files', 'release_order', 'order_manager',
           'run_all']

# Cell
from netCDF4 import Dataset
import matplotlib.pyplot as plt
from pathlib import Path
import pandas as pd
from rasterio.coords import BoundingBox, disjoint_bounds
import numpy as np
import json
import requests
import warnings
import re
import os
from fastprogress.fastprogress import progress_bar
from nbdev.imports import test_eq
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from datetime import datetime
import pdb

from .external import geturl

# Cell
class Ladsweb():
    def __init__(self, product:str, collection:str, tstart:str, tend:str,
                 bbox:list, bands:list=None, coordsOrTiles:str="coords", daynight:str="DNB",
                 repName:str='GEO', repPixSize:float=0.01, repResample:str='bilinear',
                 doMosaic:str='False', **kwargs):
        self.product, self.collection = product, collection
        self.tstart, self.tend, self.bbox, self.bands = tstart, tend, bbox, bands
        self.coordsOrTiles, self.daynight, self.repName = coordsOrTiles, daynight, repName
        self.repPixSize, self.repResample, self.doMosaic = repPixSize, repResample, doMosaic
        self._maxOrderSize, self._authFile = 1800, os.path.expanduser('~/.ladsweb')

    @property
    def _email(self):
        with open(self._authFile, 'r') as f:
            data = json.load(f)['email']
        assert len(data) > 0
        assert '@' in data
        return data

    @property
    def _key(self):
        with open(self._authFile, 'r') as f:
            data = json.load(f)['key']
        assert len(data) > 0
        return data

    def search_files(self):
        "Search for files for the product, region and time span given."
        url = (f"https://modwebsrv.modaps.eosdis.nasa.gov/axis2/services/MODAPSservices/" +
            f"searchForFiles?product={self.product}&collection={self.collection}&" +
            f"start={self.tstart}&stop={self.tend}&north={self.bbox[3]}&south={self.bbox[1]}" +
            f"&west={self.bbox[0]}&east={self.bbox[2]}&coordsOrTiles={self.coordsOrTiles}" +
            f"&dayNightBoth={self.daynight}")
        return re.findall('<return>(.*?)</return>', requests.get(url).text)

    def download_raw_files(self, path_save:Path, replace=False):
        authFile = os.path.expanduser('~/.ladsweb')
        with open(authFile, 'r') as f:
            f = json.load(f)
            email = f['email']
            auth = f['key']

        if isinstance(path_save, str):
            path_save = Path(path_save)
            path_save.mkdir(exist_ok=True, parents=True)

        # Get order ids
        print('Searching for files...')
        order_ids = self.search_files()

        # Search filenames
        filenames = []
        for order_id in progress_bar(order_ids):
            url = f'https://ladsweb.modaps.eosdis.nasa.gov/details/file/{self.collection}/{order_id}'
            # Ladsweb will sometimes return 504 timeouts, so we retry up to 10 times
            good_file = False
            for _ in range(10):
                if not good_file:
                    try:
                        file = re.findall('<td>File Name</td><td>(.*?)</td>', requests.get(url).text)[0]
                        filenames.append(file)
                        good_file = True
                    except:
                        warnings.warn(f'Unable to get {url} (most likely receieved 504 Gateway Time-out). Retrying.', UserWarning)
                        sleep(10)

        pattern = r'^\w+.A(20[0-9][0-9])([0-3][0-9][0-9])..*$'

        # Extract time from filenames
        times = []
        for f in filenames:
            x = re.search(pattern, f)
            if x is not None:
                year, doy = map(x.group, [1,2])
            times.append(pd.Timestamp(f'{year}-01-01') + pd.Timedelta(days=int(doy)-1))

        # Download Files
        print('Downloading files...')
        for filename, time in progress_bar(zip(filenames, times), total=len(filenames)):
            year = time.year
            doy = time.dayofyear
            url = f'https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/' \
                  f'{self.collection}/{self.product}/{year}/{doy:03d}/{filename}'
            fsave = f'{path_save/filename}'
            if not Path(fsave).is_file() or replace:
                good_file = False
                for _ in range(10):
                    if not good_file:
                        with open(fsave, mode='w+b') as fh:
                            try:
                                geturl(f'{url}', auth, fh)
                            except Exception as e:
                                warnings.warn(f'Unable to get {url}. Exception {e}', UserWarning)
                        try:
                            Dataset(fsave, mode='r')
                            good_file = True
                        except:
                            warnings.warn(f'Failed to open netcdf. Trying to download again.')
                            os.remove(fsave)
                            sleep(10)
            else: warnings.warn(f'{filename} already exists in {path_save} and replace is set to False')

    def order_size(self):
        "Calculates the number of files in the order."
        if self.bands is None:
            raise Exception("`bands` list required to calculate order_size.")
        return len(self.search_files())*len(self.bands)

    def split_times(self, maxOrderSize=None):
        "Split a single order into multiple orders if the order size is too large."
        if maxOrderSize is None: maxOrderSize = self._maxOrderSize
        order_size = self.order_size()
        if order_size <= maxOrderSize:
            return [self]
        n_splits = order_size // maxOrderSize + 1
        times = pd.date_range(self.tstart, self.tend)
        bk = -(len(times) % n_splits)
        if bk == 0: bk = None
        splits = np.split(times[:bk], n_splits)
        splits[-1] = splits[-1].append(times[bk:])
        times = [(str(t[0]), str(t[-1]+pd.Timedelta(days=1-1e-5).round('s'))) for t in splits]
        tstart, tend = zip(*times)
        kwargs = self.__dict__
        group = []
        for ti, tf in zip(tstart, tend):
            kwargs['tstart'], kwargs['tend'] = ti, tf
            group.append(Ladsweb(**kwargs))
        return group

    def send_order(self, ids):
        "Send order for a set of ids obtained with `search_files` method."
        ids = ','.join(ids)
        bands = ','.join([self.product + f'___{b}' for b in self.bands])
        url = (f"http://modwebsrv.modaps.eosdis.nasa.gov/axis2/services/MODAPSservices/" +
            f"orderFiles?fileIds={ids}" +
            f"&subsetDataLayer={bands}" +
            f"&geoSubsetNorth={self.bbox[3]}" +
            f"&geoSubsetSouth={self.bbox[1]}" +
            f"&geoSubsetEast={self.bbox[2]}" +
            f"&geoSubsetWest={self.bbox[0]}" +
            f"&reprojectionName={self.repName}" +
            f"&reprojectionOutputPixelSize={self.repPixSize}" +
            f"&reprojectionResampleType={self.repResample}" +
            f"&doMosaic={self.doMosaic}" +
            f"&email={self._email}")
        return re.findall('<return>(.*?)</return>', requests.get(url).text)[0]

    def run(self, path_save):
        "Send request and update log file."
        ids = self.search_files()
        if len(ids) == 0:
            warnings.warn("No files found", UserWarning)
            return
        if self.bands is None: raise Exception("A list of `bands` is not defined")
        orderId = self.send_order(ids)
        status = order_status(orderId)
        update_log(Path(path_save)/'order_log.json', orderId, status)
        print(f'New request sent with orderId {orderId}')

    def __repr__(self):
        s = ''
        for k in self.__dict__:
            s += f'{k}: {self.__dict__[k]}, '
        return s + '\n'

# Cell
def read_log(file):
    "Read log file."
    with open(file, 'r') as f:
        data = json.load(f)
    return data

def update_log(file, orderId, status):
    "Update log file."
    now = datetime.now()
    current_time = now.strftime("%Y-%m-%d_%H:%M:%S")
    if file.is_file():
        stored_data = read_log(file)
        if orderId not in [k for k in stored_data]:
            stored_data[orderId] = {'status': '', 'time': ''}
        if stored_data[orderId]['status'] != status:
            stored_data[orderId]['status'] = status
            stored_data[orderId]['time'] = current_time
    else:
        stored_data = {orderId: {'status': status, 'time': current_time}}

    with open(file, 'w') as f:
        json.dump(stored_data, f)

def order_status(orderId):
    "Check order status."
    url = (f"http://modwebsrv.modaps.eosdis.nasa.gov/axis2/services/MODAPSservices/" +
            f"getOrderStatus?orderId={orderId}")
    return re.findall('<return>(.*?)</return>', requests.get(url).text)[0]

def download_files(orderId, path_save, auth=None):
    "Download files if the order is Available."
    if auth is None: raise Exception("`auth` code is not defined")
    status = order_status(orderId)
    if status != 'Available':
        msg = f"Order is not Available, current status is {status}"
        warnings.warn(msg, UserWarning)
        return
    url = f'https://ladsweb.modaps.eosdis.nasa.gov/archive/orders/{orderId}'
    #files = pd.DataFrame(json.loads(geturl(url + '.json', auth))) # no longer available
    checksums = geturl(url + f'/checksums_{orderId}', auth)
    hdfs = re.findall('(.*?.hdf)', checksums)
    ch = [tuple([k for k in h.split(' ') if k != '']) for h in hdfs]
    files = pd.DataFrame(ch, columns=['checksum', 'size', 'name'])
    files = files.drop('size', axis=1)
    #files = pd.merge(files, check_df, how='left', on='name')
    files['verified'] = False

    for i in progress_bar(range(len(files))):
        file, checksum = files.loc[i, ['name', 'checksum']]
        csum = None
        if (Path(path_save)/file).is_file():
            csum = os.popen(f'cksum {str(path_save)}/{file}').read().split(' ')[0]
        if csum is None or checksum != csum:
            n_tries = 0
            while ~files.loc[i, 'verified'] and n_tries<5:
                #print(f'Downloading {file}')
                with open(Path(path_save)/f'{file}', mode='w+b') as fh:
                    try: geturl(f'{url}/{file}', auth, fh)
                    except: warnings.warn(f'Unable to get {url}/{file}', UserWarning)
                csum = os.popen(f'cksum {str(path_save)}/{file}').read().split(' ')[0]
                if str(checksum) == 'nan': checksum = csum
                files.loc[i, 'verified'] = checksum == csum
                n_tries += 1
        elif checksum == csum: files.loc[i, 'verified'] = True
    log_file = f'download_log_{orderId}.csv'
    files.to_csv(Path(path_save)/log_file)
    not_verified = np.sum(~files.verified)
    if not_verified > 0:
        msg = f"Checksum failed for {not_verified} files. Check the {log_file}."
        warnings.warn(msg, UserWarning)
    return not_verified

def release_order(orderId, email=None):
    "To release order after download the files."
    if email is None: raise Exception("`email` is not defined")
    url = (f"http://modwebsrv.modaps.eosdis.nasa.gov/axis2/services/MODAPSservices/" +
    f"releaseOrder?orderId={orderId}&email={email}")
    status = re.findall('<return>(.*?)</return>', requests.get(url).text)[0]
    return status == '1'

def order_manager(path_save):
    "Manage active orders in log file. Check the status and download the files for each order"
    authFile = os.path.expanduser('~/.ladsweb')
    with open(authFile, 'r') as f:
        f = json.load(f)
        email = f['email']
        auth = f['key']

    log_file = Path(path_save)/'order_log.json'
    while True:
        data = read_log(log_file)

        # Update status
        for orderId in data:
            if data[orderId]['status'] != 'Complete':
                status = order_status(orderId)
                update_log(log_file, orderId, status)

        # Download if available (wait 10 min)
        now = datetime.now()
        current_time = now.strftime("%Y%m%d_%H%M%S")
        for orderId in data:
            if data[orderId]['status'] == 'Available':
                d = (pd.Timestamp(' '.join(current_time.split('_')))
                     - pd.Timestamp(' '.join(data[orderId]['time'].split('_')))).seconds
                if d//60 > 10:
                    status = download_files(orderId, path_save, auth)
                    if status == 0:
                        result = release_order(orderId, email)
                        status = 'Complete' if result else 'One or more files not verified'
                        update_log(log_file, orderId, status)
                        print(f'Files for order {orderId} saved at {path_save}.')

        # Check if stop
        n = 0
        for orderId in data:
            if data[orderId]['status'] in ['Complete', 'One or more files not verified',
                                           'Canceled', 'Removed']:
                n += 1
        stop = len(data) == n
        if stop: return
        sleep(20)

def run_all(request_list, path_save):
    "Send a list of requests and initiate order manager."
    for request in request_list:
        request.run(path_save)
        sleep(5)
    order_manager(path_save)