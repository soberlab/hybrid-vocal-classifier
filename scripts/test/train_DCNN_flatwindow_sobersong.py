### Note this is Python 2.7, because Theano ###
from __future__ import division

import os
import glob
import datetime
import shelve

import numpy as np
from scipy.io import wavfile
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold
from keras.utils.np_utils import to_categorical
from keras.callbacks import ModelCheckpoint, CSVLogger, EarlyStopping

import hvc.utils.utils
import hvc.neuralnet.models
from hvc.utils import sequences
from hvc.audio.evfuncs import load_cbin,load_notmat

#constants for spectrogram
SAMP_FREQ = 32000 # Hz
WINDOW_SIZE= 512
WINDOW_STEP= 32
FREQ_CUTOFFS=[1000,8000]
MAX_SILENT_GAP = 0.08 # s to keep before or after a syllable

# constants used by script
BIRD_ID = 'bl26lb16'
DATA_DIR = os.path.normpath('C:/DATA/bl26lb16/pre_surgery_baseline/042012/')
OUTPUT_DIR = os.path.normpath('C:/DATA/bl26lb16/hvc_neuralnet_results/')
#NUM_SONGS_TO_USE = 6
LABELS_TO_USE = list('abcdefghijk')

os.chdir(DATA_DIR)
cbins = glob.glob('*.cbin')

#given that there's only one sampling frequency, use it to figure out the number of time bins in the
#fixed length spectrogram into which the sequences will be padded
timebin_size_in_s = WINDOW_STEP / SAMP_FREQ # for default, 32 / 32000 = 0.001 s, i.e. 1 ms

MAX_SPECT_WIDTH = 300; # time bins of spect, currently ~ 1ms

all_syl_labels = []
all_syl_spects = []
background_noise = []
for cbin_ind,cbin in enumerate(cbins):
    print('extracting syllables from song {} of {}\r'.format(cbin_ind,
                                                             len(cbins)))
    dat, fs = load_cbin(cbin)
    if fs != SAMP_FREQ:
        raise ValueError(
            'Sampling frequency for {}, {}, does not match expected sampling '
            'frequency of {}'.format(cbin,
                                     fs,
                                     SAMP_FREQ))
    dat,fs = load_cbin(cbin)
    spect_obj = hvc.utils.utils.make_spect(dat,fs,
                                           size=WINDOW_SIZE,
                                           step=WINDOW_STEP,
                                           freq_cutoffs=FREQ_CUTOFFS)
    spect = spect_obj.spect     
    time_bins = spect_obj.timeBins

    notmat = load_notmat(cbin)
    labels = notmat['labels']
    onsets = notmat['onsets'] / 1000.0
    offsets = notmat['offsets'] / 1000.0
    onsets_time_bins = [np.argmin(np.abs(time_bins - onset))
                                for onset in onsets]
    offsets_time_bins = [np.argmin(np.abs(time_bins - offset))
                                for offset in offsets]
    #extract each syllable, but include the "silence" around it
    for ind,label in enumerate(labels):
        if label not in LABELS_TO_USE:
            continue
        temp_syl_spect = spect[:,onsets_time_bins[ind]:offsets_time_bins[ind]]
        width_diff = MAX_SPECT_WIDTH - temp_syl_spect.shape[1]
        # take half of difference between spects and make that the start index
        # so one half of 'empty' area will be on one side of spect
        # and the other half will be on other side
        # i.e., center the spectrogram
        left_width = int(round(width_diff / 2))
        right_width = width_diff - left_width
        if left_width > onsets_time_bins[ind]:
            left_width = onsets_time_bins[ind]
            right_width = width_diff - left_width
        elif offsets_time_bins[ind] + right_width > spect.shape[-1]:
            right_width = spect.shape[-1] - offsets_time_bins[ind]
            left_width = width_diff - right_width
        temp_syl_spect = spect[:,onsets_time_bins[ind]-left_width:
                                 offsets_time_bins[ind]+right_width]
        all_syl_labels.append(label)
        all_syl_spects.append(temp_syl_spect)

#scale all spects by mean and std of training set
spect_scaler = StandardScaler()
# concatenate all spects then rotate  so Hz bins are 'features'
spect_scaler.fit(np.rot90(np.hstack(all_syl_spects[:])))
# now scale each individual training spect
all_syl_spects_scaled = []
for spect in all_syl_spects:
    all_syl_spects_scaled.append(
        np.rot90(
            spect_scaler.transform(np.rot90(spect))
            ,3)
            )

#reshape training data for model
all_syl_spects = np.stack(all_syl_spects_scaled[:],axis=0)
all_syl_spects = np.expand_dims(all_syl_spects,axis=1)

num_syl_classes = np.size(LABELS_TO_USE)
# make a dictionary that maps labels to classes 0 to n-1 where n is number of
# classes of syllables.
# Need this map instead of e.g. converting from char to int because
# keras to_categorical function requires
# input where classes are labeled from 0 to n-1
classes_zero_to_n = range(num_syl_classes)
label_map = dict(zip(LABELS_TO_USE,classes_zero_to_n))
all_syl_labels_zero_to_n = np.asarray([label_map[syl]
                                        for syl in all_syl_labels])
#so we can then convert to array of binary / one-hot vectors for training
all_syl_labels_binary = to_categorical(all_syl_labels_zero_to_n,num_syl_classes)

num_syl_spects = all_syl_spects.shape[0]
half_spects = num_syl_spects // 2

train_spects = all_syl_spects[:half_spects,:,:,:]
train_labels = all_syl_labels_binary[:half_spects,:]

validat_spects = all_syl_spects[half_spects:,:,:,:]
validat_labels = all_syl_labels_binary[half_spects:,:]

#print('Shuffling syllables.')
## shuffle and split into training and test sets
#RANDOM_SEED = 42 
#np.random.seed(RANDOM_SEED) 
#shuffle_ids = np.random.permutation(all_syl_spects.shape[0])
#all_syl_spects_shuffled = all_syl_spects[shuffle_ids,:,:,:]
#all_syl_labels_shuffled = all_syl_labels_binary[shuffle_ids,:]

#constants for training
NUM_TRAIN_SAMPLES = 100
train_spects_subset = train_spects[:NUM_TRAIN_SAMPLES,:,:,:]
train_labels_subset = train_labels[:NUM_TRAIN_SAMPLES,:]


uniq_syls, syl_counts = np.unique(all_syl_labels[:NUM_TRAIN_SAMPLES],
                                  return_counts=True)
print('Training set:')
for syl,count in zip(uniq_syls,syl_counts):
    print('\tSyllable {} -- {} samples.'.format(syl,count)) 

# Also need to know number of rows, i.e. freqbins.
# Will be the same for all spects since we used the same FFT params for all.
# freqBins size is also input shape to LSTM net
# (since at each time point the input is one column of spectrogram)
num_channels,num_freqbins, num_timebins = all_syl_spects[0].shape
input_shape = (num_channels,num_freqbins,num_timebins)
flatwindow = hvc.neuralnet.models.DCNN_flatwindow(input_shape=input_shape,
                                   num_syllable_classes=num_syl_classes) 

now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
num_samples = "_" + str(NUM_TRAIN_SAMPLES) + "_samples"
filename = BIRD_ID + '_' + 'DCNN_flatwindow_training_' + now_str + num_samples + '.log'
csv_logger = CSVLogger(filename,
                       separator=',',
                       append=True)
weights_filename= BIRD_ID + '_' + "weights " + now_str + num_samples + ".best.hdf5"
checkpoint = ModelCheckpoint(weights_filename,
                             monitor='val_acc',
                             verbose=1,
                             save_best_only=True,
                             save_weights_only=True,
                             mode='max')
earlystop = EarlyStopping(monitor='val_acc',
                          min_delta=0,
                          patience=20,
                          verbose=1,
                          mode='auto')
callbacks_list = [csv_logger,checkpoint,earlystop]

BATCH_SIZE = 32
NB_EPOCH = 200

if not os.path.isdir(OUTPUT_DIR):
    os.mkdir(OUTPUT_DIR)
os.chdir(OUTPUT_DIR)
print('Training model.')
flatwindow.fit(train_spects_subset,
          train_labels_subset,
          validation_data=(validat_spects,validat_labels),
          batch_size=BATCH_SIZE,
          nb_epoch=NB_EPOCH,
          callbacks=callbacks_list,
          verbose=1)

shelve_fname = BIRD_ID + '_' + now_str + num_samples + "_training_set_data"
with shelve.open(shelve_fname) as shv:
    shv['data_dir'] = DATA_DIR
#    shv['num_songs_to_use'] = NUM_SONGS_TO_USE
    shv['cbins'] = cbins
#    shv['shuffle_ids'] = shuffle_ids
    shv['half_of_spects'] = half_spects
    shv['num_train_samples'] = NUM_TRAIN_SAMPLES
#    shv['validation_split'] = VALIDAT_SPLIT
    shv['batch_size'] = BATCH_SIZE
    shv['nb_epoch'] = NB_EPOCH
# save: all_syl_labels, all_syl_labels_shuffled, label_map, etc....
# train lables and train spects of course
