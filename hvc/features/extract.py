import collections
import warnings

import numpy as np

from . import tachibana, knn
from hvc import audiofileIO

single_syl_features_switch_case_dict = {
    'mean spectrum': tachibana.mean_spectrum,
    'mean delta spectrum': tachibana.mean_delta_spectrum,
    'mean cepstrum': tachibana.mean_cepstrum,
    'mean delta cepstrum': tachibana.mean_delta_cepstrum,
    'duration': tachibana.duration,
    'mean spectral centroid': tachibana.mean_spectral_centroid,
    'mean spectral spread': tachibana.mean_spectral_spread,
    'mean spectral skewness': tachibana.mean_spectral_skewness,
    'mean spectral kurtosis': tachibana.mean_spectral_kurtosis,
    'mean spectral flatness': tachibana.mean_spectral_flatness,
    'mean spectral slope': tachibana.mean_spectral_slope,
    'mean pitch': tachibana.mean_pitch,
    'mean pitch goodness': tachibana.mean_pitch_goodness,
    'mean delta spectral centroid': tachibana.mean_delta_spectral_centroid,
    'mean delta spectral spread': tachibana.mean_delta_spectral_spread,
    'mean delta spectral skewness': tachibana.mean_delta_spectral_skewness,
    'mean delta spectral kurtosis': tachibana.mean_delta_spectral_kurtosis,
    'mean delta spectral flatness': tachibana.mean_delta_spectral_flatness,
    'mean delta spectral slope': tachibana.mean_delta_spectral_slope,
    'mean delta pitch': tachibana.mean_delta_pitch,
    'mean delta pitch goodness': tachibana.mean_delta_pitch_goodness,
    'zero crossings': tachibana.zero_crossings,
    'mean amplitude': tachibana.mean_amplitude,
    'mean delta amplitude': tachibana.mean_delta_amplitude,
    'mean smoothed rectified amplitude': knn.mn_amp_smooth_rect,
    'mean RMS amplitude': knn.mn_amp_rms,
    'mean spectral entropy': knn.mean_spect_entropy,
    'mean hi lo ratio': knn.mean_hi_lo_ratio,
    'delta smoothed rectified amplitude': knn.delta_amp_smooth_rect,
    'delta spectral entropy': knn.delta_entropy,
    'delta hi lo ratio': knn.delta_hi_lo_ratio
}

multiple_syl_features_switch_case_dict = {
    'duration group': knn.duration,
    'preceding syllable duration': knn.pre_duration,
    'following syllable duration': knn.foll_duration,
    'preceding silent gap duration': knn.pre_gapdur,
    'following silent gap duration': knn.foll_gapdur
 }


def from_file(filename,
              file_format,
              feature_list,
              spect_params,
              labels_to_use,
              segment_params
              ):
    """
    extracts features from an audio file containing birdsong
    
    Parameters
    ----------
    filename : str
        audio file
    file_format : str
        'evtaf' or 'koumura'
    feature_list : list of strings
        list of features to extract from each sound segment
        Defined in config file, generated by hvc.parse.extract
    spect_params : dict
        parameters for generating spectrogram
        see Spectrogram.__init__ or parse.extract docstring
        for definitions.
        Defined in config file, generated by hvc.parse.extract
    labels_to_use : str
        either string of labels, e.g., 'iabcdef' or '012345'
        or 'all'
        Defined in config file, generated by hvc.parse.extract
    segment_params : dict
        Defined in config file, generated by hvc.parse.extract
        e.g. when using segments from an annotation file

    Returns
    -------
    features_arr : m-by-n numpy array
        where each column n is a feature or one element of a multi-column feature
        (e.g. spectrum is a multi-column feature)
        and each row m represents one syllable
    labels : list of chars
        of length m, one label for each syllable in features_arr
    feature_inds : 1-d numpy array of ints
        indexing array used by hvc/extract to split feature_arr back up into
        feature groups
        Array will be of length n where n is number of columns in features_arr,
        but unique(feature_inds) = len(feature_list)
    """

    song = audiofileIO.Song(filename, file_format, segment_params)
    song.set_syls_to_use(labels_to_use)

    if np.all(song.syls_to_use == False):
        warnings.warn('No labels in {0} matched labels to use: {1}\n'
                      'Did not extract features from file.'
                      .format(filename, labels_to_use))
        return None, None, None

    # initialize indexing array for features
    # used to split back up into feature groups
    feature_inds = []

    # loop through features first instead of syls because
    # some features do not require making spectrogram
    for ftr_ind, current_feature in enumerate(feature_list):
        # if this is a feature extracted from a single syllable, i.e.,
        # if this feature requires a spectrogram
        if current_feature in single_syl_features_switch_case_dict:
            if not hasattr(song, 'syls'):
                song.make_syl_spects(spect_params)
            if 'curr_feature_arr' in locals():
                del curr_feature_arr

            for ind, syl in enumerate(song.syls):
                if syl.spect is np.nan:
                    # can't extract feature so leave as nan
                    continue
                # extract current feature from every syllable
                ftr = single_syl_features_switch_case_dict[current_feature](syl)
                if 'curr_feature_arr' in locals():
                    if np.isscalar(ftr):
                        curr_feature_arr[ind] = ftr
                    else:
                        # note have to add dimension with newaxis because np.concat requires
                        # same number of dimensions, but extract_features returns 1d.
                        # Decided to keep it explicit that we go to 2d here.
                        curr_feature_arr[ind, :] = ftr[np.newaxis, :]
                else:  # if curr_feature_arr doesn't exist yet
                    # initialize vector, if feature is a scalar, or matrix, if feature is a vector
                    # where each element (scalar feature) or row (vector feature) is feature from
                    # one syllable.
                    # Initialize as nan so that if there are syllables from which feature could
                    # not be extracted, the value for that feature stays as nan
                    # (e.g. because segment was too short to make spectrogram
                    # with given spectrogram values)
                    if np.isscalar(ftr):
                        curr_feature_arr = np.full((len(song.syls)), np.nan)
                        # may not be on first syllable if first spectrogram was nan
                        # so need to index into initialized array
                        curr_feature_arr[ind] = ftr
                    else:
                        curr_feature_arr = np.full((len(song.syls),
                                                    ftr.shape[-1]), np.nan)
                        # may not be on first syllable if first spectrogram was nan
                        # so need to index into initialized array
                        curr_feature_arr[ind, :] = ftr[np.newaxis, :]  # make 2-d for concatenate

            # after looping through all syllables:
            if 'features_arr' in locals():
                if np.isscalar(ftr):
                    # if feature is scalar,
                    # then `ftr` from all syllables will be a (row) vector
                    # so transpose to column vector then add to growing end of 2d matrix
                    feature_inds.extend([ftr_ind])
                    features_arr = np.concatenate((features_arr,
                                                   curr_feature_arr[np.newaxis, :].T),
                                                  axis=1)
                else:
                    # if feature is not scalar,
                    # `ftr` will be 2-d, so don't transpose before you concatenate
                    feature_inds.extend([ftr_ind] * ftr.shape[-1])
                    features_arr = np.concatenate((features_arr,
                                                   curr_feature_arr),
                                                  axis=1)
            else:  # if 'features_arr' doesn't exist yet
                if np.isscalar(ftr):
                    feature_inds.extend([ftr_ind])
                else:
                    feature_inds.extend([ftr_ind] * ftr.shape[-1])
                features_arr = curr_feature_arr

        elif current_feature in multiple_syl_features_switch_case_dict:
            curr_feature_arr = multiple_syl_features_switch_case_dict[current_feature](song.onsets_s,
                                                                                       song.offsets_s,
                                                                                       song.syls_to_use)
            feature_inds.extend([ftr_ind])
            if 'features_arr' in locals():
                features_arr = np.concatenate((features_arr,
                                               curr_feature_arr[:,np.newaxis]),
                                              axis=1)
            else:
                features_arr = curr_feature_arr
    labels = [label for label in song.labels if label in labels_to_use]
    return features_arr, labels, np.asarray(feature_inds)
