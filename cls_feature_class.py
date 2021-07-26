# Contains routines for labels creation, features extraction and normalization
#


import os
import numpy as np
import scipy.io.wavfile as wav
from sklearn import preprocessing
import joblib
from IPython import embed
import matplotlib.pyplot as plot
import librosa
plot.switch_backend('agg')
import shutil
import math
import os, sys
import scipy.io.wavfile as wav
from subprocess import call
import numpy as np
import pickle
import scipy.io
from srmrpy import srmr
from scipy import io, polyval, polyfit, sqrt, stats, signal
import tables
import librosa

def nCr(n, r):
    return math.factorial(n) // math.factorial(r) // math.factorial(n-r)


class FeatureClass:
    def __init__(self, params, is_eval=False):
        """

        :param params: parameters dictionary
        :param is_eval: if True, does not load dataset labels.
        """

        # Input directories
        self._feat_label_dir = params['feat_label_dir']
        self._dataset_dir = params['dataset_dir']
        self._dataset_combination = '{}_{}'.format(params['dataset'], 'eval' if is_eval else 'dev')
        self._aud_dir = os.path.join(self._dataset_dir, self._dataset_combination)
        
        self._desc_dir = None if is_eval else os.path.join(self._dataset_dir, 'metadata_dev')

        # Output directories
        self._label_dir = None
        self._feat_dir = None
        self._feat_dir_norm = None

        # Local parameters
        self._is_eval = is_eval

        self._fs = params['fs']
        self._hop_len_s = params['hop_len_s']
        self._hop_len = int(self._fs * self._hop_len_s)

        self._label_hop_len_s = params['label_hop_len_s']
        self._label_hop_len = int(self._fs * self._label_hop_len_s)
        self._label_frame_res = self._fs / float(self._label_hop_len)
        self._nb_label_frames_1s = int(self._label_frame_res)

        self._win_len = 2 * self._hop_len
        self._nfft = self._next_greater_power_of_2(self._win_len)

        self._nb_mel_bins = params['nb_mel_bins']
        self._nb_mel_bins1 = params['nb_mel_bins1']
        
        self._mel_wts1 = librosa.filters.mel(sr=self._fs, n_fft=self._nfft, n_mels=self._nb_mel_bins1).T
        self._nb_mel_bins2 = params['nb_mel_bins2']
        self._mel_wts2 = librosa.filters.mel(sr=self._fs, n_fft=self._nfft, n_mels=self._nb_mel_bins2).T
        self._mel_wts = librosa.filters.mel(sr=self._fs, n_fft=self._nfft, n_mels=self._nb_mel_bins).T
        self._dataset = params['dataset']
        self._eps = 1e-8
        self._nb_channels = 4

        # Sound event classes dictionary
        self._unique_classes = params['unique_classes']
        self._audio_max_len_samples = params['max_audio_len_s'] * self._fs  # TODO: Fix the audio synthesis code to always generate 60s of
        # audio. Currently it generates audio till the last active sound event, which is not always 60s long. This is a
        # quick fix to overcome that. We need this because, for processing and training we need the length of features
        # to be fixed.

        self._max_feat_frames = int(np.ceil(self._audio_max_len_samples / float(self._hop_len)))
        self._max_label_frames = int(np.ceil(self._audio_max_len_samples / float(self._label_hop_len)))

    def _load_audio(self, audio_path):
        fs, audio = wav.read(audio_path)
        audio = audio[:, :self._nb_channels] / 32768.0 + self._eps
        if audio.shape[0] < self._audio_max_len_samples:
            zero_pad = np.random.rand(self._audio_max_len_samples - audio.shape[0], audio.shape[1])*self._eps
            audio = np.vstack((audio, zero_pad))
        elif audio.shape[0] > self._audio_max_len_samples:
            audio = audio[:self._audio_max_len_samples, :]
        return audio, fs

    # INPUT FEATURES
    @staticmethod
    def _next_greater_power_of_2(x):
        return 2 ** (x - 1).bit_length()

    def _spectrogram(self, audio_input):
        _nb_ch = audio_input.shape[1]
        nb_bins = self._nfft // 2
        print('n_ffft', nb_bins)
        spectra = np.zeros((self._max_feat_frames, nb_bins + 1, _nb_ch), dtype=complex)
        for ch_cnt in range(_nb_ch):
            stft_ch = librosa.core.stft(np.asfortranarray(audio_input[:, ch_cnt]), n_fft=self._nfft, hop_length=self._hop_len,
                                        win_length=self._win_len, window='hann')
            spectra[:, :, ch_cnt] = stft_ch[:, :self._max_feat_frames].T
        print('sepctra',spectra.shape)
        return spectra

    def _get_mel_spectrogram(self, linear_spectra):
        mel_feat = np.zeros((linear_spectra.shape[0], self._nb_mel_bins1, linear_spectra.shape[-1]))
        print('linear spectra', linear_spectra.shape[0],linear_spectra.shape[-1])
        for ch_cnt in range(linear_spectra.shape[-1]):
            mag_spectra = np.abs(linear_spectra[:, :, ch_cnt])**2
            mel_spectra = np.dot(mag_spectra, self._mel_wts1)
            log_mel_spectra = librosa.power_to_db(mel_spectra)
            print('log mel dimention', log_mel_spectra.shape)
            mel_feat[:, :, ch_cnt] = log_mel_spectra
        print('mel spect shape before transfomation', mel_feat.shape)
        print('transpose mel spec', mel_feat.transpose((0, 2, 1)).shape)
        print('reshape mel with linear spect',(linear_spectra.shape[0], -1))
        mel_feat = mel_feat.transpose((0, 2, 1)).reshape((linear_spectra.shape[0], -1))
        print('final mel_feat shape', mel_feat.shape)
        return mel_feat
     
    def srmr_final_energy(self, audio_input, FS=16000):
    

        fs, s = wav.read(audio_input)
        nb_ch = s.shape[1]
        print('channels', nb_ch)

        if (fs != FS):
            n_s = round(len(s) * (FS / fs))
            s = signal.resample(s, n_s)
        ratio, energy, n_frames = srmr(s[:,0], FS)
       
        final_energy = np.zeros((n_frames,184,4))
        for ch_cnt in range(nb_ch):
            out = s[:,ch_cnt]
            ratio, energy, n_frames = srmr(out, FS)
            print(energy.shape)
            mod = np.reshape(energy, (energy.shape[2], energy.shape[0] * energy.shape[1]))
            print(mod.shape)
      
            final_energy[:,:,ch_cnt] = mod
        
        return final_energy
    
    def srmr_audio(self, audio_input, FS=16000):
    

        fs, s = wav.read(audio_input)
        nb_ch = s.shape[1]
        print('channels', nb_ch)

        if (fs != FS):
            n_s = round(len(s) * (FS / fs))
            s = signal.resample(s, n_s)
        ratio, energy, n_frames = srmr(s[:,0], FS)
        print('n_frames', n_frames)
        final_energy = np.zeros((n_frames,184,4))
        for ch_cnt in range(nb_ch):
            out = s[:,ch_cnt]
            ratio, energy, n_frames = srmr(out, FS)
            print(energy.shape)
            mod = np.reshape(energy, (energy.shape[2], energy.shape[0] * energy.shape[1]))
            print(mod.shape)
      
            final_energy[:,:,ch_cnt] = mod
        print('final_energy', final_energy.shape)
        SRMR_mod_feat = final_energy.transpose((0, 2, 1)).reshape((final_energy.shape[0], -1))
        return SRMR_mod_feat

    def _get_foa_intensity_vectors(self, linear_spectra):
        print('linear_spectra',linear_spectra.shape)
        IVx = np.real(np.conj(linear_spectra[:, :, 0]) * linear_spectra[:, :, 3])
        IVy = np.real(np.conj(linear_spectra[:, :, 0]) * linear_spectra[:, :, 1])
        IVz = np.real(np.conj(linear_spectra[:, :, 0]) * linear_spectra[:, :, 2])

        normal = self._eps + (np.abs(linear_spectra[:, :, 0])**2 + np.abs(linear_spectra[:, :, 1])**2 + np.abs(linear_spectra[:, :, 2])**2 + np.abs(linear_spectra[:, :, 3])**2)/2.
        #normal = np.sqrt(IVx**2 + IVy**2 + IVz**2) + self._eps
        IVx = np.dot(IVx / normal, self._mel_wts)
        IVy = np.dot(IVy / normal, self._mel_wts)
        IVz = np.dot(IVz / normal, self._mel_wts)
        print('intensity vec', IVx.shape, IVy.shape,IVz.shape)
        mel_weights = self._mel_wts
        print('mel_weights',mel_weights.shape)
        # we are doing the following instead of simply concatenating to keep the processing similar to mel_spec and gcc
        foa_iv = np.dstack((IVx, IVy, IVz))
        print('foa_iv',foa_iv.shape)
        foa_iv = foa_iv.transpose((0, 2, 1)).reshape((linear_spectra.shape[0], -1))
        print('foa2',foa_iv.shape)
        if np.isnan(foa_iv).any():
            print('Feature extraction is generating nan outputs')
            exit()
        return foa_iv




    def _get_foa_mod_intensity_vectors(self, final_energy):
        print('final_energy',final_energy.shape)
        IVx = np.real(np.conj(final_energy[:, :, 0]) * final_energy[:, :, 3])
        IVy = np.real(np.conj(final_energy[:, :, 0]) * final_energy[:, :, 1])
        IVz = np.real(np.conj(final_energy[:, :, 0]) * final_energy[:, :, 2])

        
        print('intensity vec', IVx.shape, IVy.shape,IVz.shape)
        # we are doing the following instead of simply concatenating to keep the processing similar to mel_spec and gcc
        foa_iv = np.dstack((IVx, IVy, IVz))
        print('foa_iv mod',foa_iv.shape)
        foa_iv_mod = foa_iv.transpose((0, 2, 1)).reshape((final_energy.shape[0], -1))
        print('foa2 mod',foa_iv_mod.shape)
        if np.isnan(foa_iv_mod).any():
            print('Feature extraction is generating nan outputs')
            exit()
        return foa_iv_mod

    def _get_gcc(self, linear_spectra):
        gcc_channels = nCr(linear_spectra.shape[-1], 2)
        print('gcc_channels',gcc_channels)
        gcc_feat = np.zeros((linear_spectra.shape[0], self._nb_mel_bins1, gcc_channels))
        print('gcc_feat',gcc_feat.shape)
        cnt = 0
        print('gcc', linear_spectra.shape[-1])
        for m in range(linear_spectra.shape[-1]):
            for n in range(m+1, linear_spectra.shape[-1]):
                R = np.conj(linear_spectra[:, :, m]) * linear_spectra[:, :, n]
                print('R',R.shape)
                cc = np.fft.irfft(np.exp(1.j*np.angle(R)))
                print('cc before', cc.shape)
                cc = np.concatenate((cc[:, -self._nb_mel_bins1//2:], cc[:, :self._nb_mel_bins1//2]), axis=-1)
                print('cc AFTER', cc.shape)
                gcc_feat[:, :, cnt] = cc
                cnt += 1
        print(gcc_feat.transpose((0, 2, 1)).shape)
        return gcc_feat.transpose((0, 2, 1)).reshape((linear_spectra.shape[0], -1))

    def _get_mod_gcc(self, final_energy):
        gcc_channels1 = nCr(final_energy.shape[-1], 2)
        print('gcc_channels1',gcc_channels1)
        gcc_feat1 = np.zeros((final_energy.shape[0], self._nb_mel_bins2, gcc_channels1))
        print('gcc_feat1',gcc_feat1.shape)
        cnt = 0
        print('gcc1', final_energy.shape[-1])
        for m in range(final_energy.shape[-1]):
            for n in range(m+1, final_energy.shape[-1]):
                R1 = np.conj(final_energy[:, :, m]) * final_energy[:, :, n]
                print('R',R1.shape)
                cc1 = np.fft.irfft(np.exp(1.j*np.angle(R1)))
                print('cc before', cc1.shape)
                cc1 = np.concatenate((cc1[:, -self._nb_mel_bins2//2:], cc1[:, :self._nb_mel_bins2//2]), axis=-1)
                print('cc AFTER', cc1.shape)
                gcc_feat1[:, :, cnt] = cc1
                cnt += 1
        print(gcc_feat1.transpose((0, 2, 1)).shape)
        return gcc_feat1.transpose((0, 2, 1)).reshape((final_energy.shape[0], -1))

    def _get_spectrogram_for_file(self, audio_path):
        audio_in, fs = self._load_audio(audio_path)
        audio_spec = self._spectrogram(audio_in)
        return audio_spec
    

    
    # OUTPUT LABELS
    def get_labels_for_file(self, _desc_file):
        """
        Reads description file and returns classification based SED labels and regression based DOA labels

        :param _desc_file: metadata description file
        :return: label_mat: labels of the format [sed_label, doa_label],
        where sed_label is of dimension [nb_frames, nb_classes] which is 1 for active sound event else zero
        where doa_labels is of dimension [nb_frames, 3*nb_classes], nb_classes each for x, y, z axis,
        """

        se_label = np.zeros((self._max_label_frames, len(self._unique_classes)))
        print('se_label',se_label.shape)
        x_label = np.zeros((self._max_label_frames, len(self._unique_classes)))
        y_label = np.zeros((self._max_label_frames, len(self._unique_classes)))
        z_label = np.zeros((self._max_label_frames, len(self._unique_classes)))
        print('x label',x_label.shape,y_label.shape,z_label.shape)
        for frame_ind, active_event_list in _desc_file.items():
            if frame_ind < self._max_label_frames:
                for active_event in active_event_list:
                    se_label[frame_ind, active_event[0]] = 1
                    x_label[frame_ind, active_event[0]] = active_event[1]
                    y_label[frame_ind, active_event[0]] = active_event[2]
                    z_label[frame_ind, active_event[0]] = active_event[3]

        label_mat = np.concatenate((se_label, x_label, y_label, z_label), axis=1)
        print('label_mat',label_mat)
        return label_mat

    # ------------------------------- EXTRACT FEATURE AND PREPROCESS IT -------------------------------
    def extract_all_feature_mel(self):
        # setting up folders
        self._feat_dir1 = self.get_unnormalized_feat_dir1()
        create_folder(self._feat_dir1)

        # extraction starts
        print('Extracting spectrogram:')
        print('\t\taud_dir {}\n\t\tdesc_dir {}\n\t\tfeat_dir {}'.format(
            self._aud_dir, self._desc_dir, self._feat_dir))
        for split in os.listdir(self._aud_dir):
            print('Split: {}'.format(split))
            for file_cnt, file_name in enumerate(os.listdir(os.path.join(self._aud_dir, split))):
                print('file_cnt', file_cnt)
                print('file_name',file_name)
                wav_filename = '{}.wav'.format(file_name.split('.')[0])

                spect = self._get_spectrogram_for_file(os.path.join(self._aud_dir, split, wav_filename))
                print('linear spect dimension', spect.shape)
                #extract mel
                mel_spect = self._get_mel_spectrogram(spect)
                print('mel_spec',mel_spect.shape)
              
                feat = None
                if self._dataset is 'foa':
                    # extract intensity vectors
                    foa_iv = self._get_foa_intensity_vectors(spect)
                    
                    print('mel_spect',mel_spect[:-1, :].shape)
                   
                    print('foa_iv',foa_iv.shape) 
                    feat = np.concatenate((mel_spect[:-1, :], foa_iv[:-1, :]), axis=-1)
                  
                elif self._dataset is 'mic':
                    # extract gcc
                    gcc = self._get_gcc(spect)
                  
                    print('gcc',gcc[:-4, :].shape)
               
                    feat = np.concatenate((mel_spect[:-4, :], gcc[:-4, :]), axis=-1)
                    print('feat',feat.shape)
                else:
                    print('ERROR: Unknown dataset format {}'.format(self._dataset))
                    exit()

                if feat is not None:
                    print('\t{}: {}, {}'.format(file_cnt, file_name, feat.shape ))
                    np.save(os.path.join(self._feat_dir1, '{}.npy'.format(wav_filename.split('.')[0])), feat)


    def extract_all_feature_mod(self):
        # setting up folders
        self._feat_dir2 = self.get_unnormalized_feat_dir2()
        create_folder(self._feat_dir2)

        # extraction starts
        print('Extracting spectrogram:')
        print('\t\taud_dir {}\n\t\tdesc_dir {}\n\t\tfeat_dir {}'.format(
            self._aud_dir, self._desc_dir, self._feat_dir))
        for split in os.listdir(self._aud_dir):
            print('Split: {}'.format(split))
            for file_cnt, file_name in enumerate(os.listdir(os.path.join(self._aud_dir, split))):
                print('file_cnt', file_cnt)
                print('file_name',file_name)
                wav_filename = '{}.wav'.format(file_name.split('.')[0])

                spect = self._get_spectrogram_for_file(os.path.join(self._aud_dir, split, wav_filename))
                print('linear spect dimension', spect.shape)
                #extract mel
                
                SRMR_mod_spec = self.srmr_audio(os.path.join(self._aud_dir, split, wav_filename))
                print('srmr mod spec',SRMR_mod_spec.shape)
                final_energy = self.srmr_final_energy(os.path.join(self._aud_dir, split, wav_filename))
                feat = None
                if self._dataset is 'foa':
                    
                    feat = SRMR_mod_spec
                  
                elif self._dataset is 'mic':
                    # extract gcc
                  
                    feat = SRMR_mod_spec
                    print('feat',feat.shape)
                else:
                    print('ERROR: Unknown dataset format {}'.format(self._dataset))
                    exit()

                if feat is not None:
                    print('\t{}: {}, {}'.format(file_cnt, file_name, feat.shape ))
                    np.save(os.path.join(self._feat_dir2, '{}.npy'.format(wav_filename.split('.')[0])), feat)

    def preprocess_features_mel(self):
        # Setting up folders and filenames
        self._feat_dir1 = self.get_unnormalized_feat_dir1()
        self._feat_dir_norm1 = self.get_normalized_feat_dir1()
        create_folder(self._feat_dir_norm1)
        normalized_features_wts_file1 = self.get_normalized_wts_file1()
        spec_scaler = None

        # pre-processing starts
        if self._is_eval:
            spec_scaler = joblib.load(normalized_features_wts_file1)
            print('Normalized_features_wts_file: {}. Loaded.'.format(normalized_features_wts_file1))

        else:
            print('Estimating weights for normalizing feature files:')
            print('\t\tfeat_dir: {}'.format(self._feat_dir))

            spec_scaler = preprocessing.StandardScaler()
            for file_cnt, file_name in enumerate(os.listdir(self._feat_dir1)):
                print('{}: {}'.format(file_cnt, file_name))
                feat_file = np.load(os.path.join(self._feat_dir1, file_name))
                spec_scaler.partial_fit(feat_file)
                del feat_file
            joblib.dump(
                spec_scaler,
                normalized_features_wts_file1
            )
            print('Normalized_features_wts_file: {}. Saved.'.format(normalized_features_wts_file1))

        print('Normalizing feature files:')
        print('\t\tfeat_dir_norm {}'.format(self._feat_dir_norm1))
        for file_cnt, file_name in enumerate(os.listdir(self._feat_dir1)):
            print('{}: {}'.format(file_cnt, file_name))
            feat_file = np.load(os.path.join(self._feat_dir1, file_name))
            feat_file = spec_scaler.transform(feat_file)
            np.save(
                os.path.join(self._feat_dir_norm1, file_name),
                feat_file
            )
            del feat_file

        print('normalized files written to {}'.format(self._feat_dir_norm1))


    def preprocess_features_mod(self):
        # Setting up folders and filenames
        self._feat_dir2 = self.get_unnormalized_feat_dir2()
        self._feat_dir_norm2 = self.get_normalized_feat_dir2()
        create_folder(self._feat_dir_norm2)
        normalized_features_wts_file2 = self.get_normalized_wts_file2()
        spec_scaler = None

        # pre-processing starts
        if self._is_eval:
            spec_scaler = joblib.load(normalized_features_wts_file2)
            print('Normalized_features_wts_file: {}. Loaded.'.format(normalized_features_wts_file2))

        else:
            print('Estimating weights for normalizing feature files:')
            print('\t\tfeat_dir: {}'.format(self._feat_dir2))

            spec_scaler = preprocessing.StandardScaler()
            for file_cnt, file_name in enumerate(os.listdir(self._feat_dir2)):
                print('{}: {}'.format(file_cnt, file_name))
                feat_file = np.load(os.path.join(self._feat_dir2, file_name))
                spec_scaler.partial_fit(feat_file)
                del feat_file
            joblib.dump(
                spec_scaler,
                normalized_features_wts_file2
            )
            print('Normalized_features_wts_file: {}. Saved.'.format(normalized_features_wts_file2))

        print('Normalizing feature files:')
        print('\t\tfeat_dir_norm {}'.format(self._feat_dir_norm2))
        for file_cnt, file_name in enumerate(os.listdir(self._feat_dir2)):
            print('{}: {}'.format(file_cnt, file_name))
            feat_file = np.load(os.path.join(self._feat_dir2, file_name))
            feat_file = spec_scaler.transform(feat_file)
            np.save(
                os.path.join(self._feat_dir_norm2, file_name),
                feat_file
            )
            del feat_file

        print('normalized files written to {}'.format(self._feat_dir_norm2))

    def concatinate_features_mel_mod(self):
      
        self._feat_dir_norm1 = self.get_normalized_feat_dir1()
        self._feat_dir_norm2 = self.get_normalized_feat_dir2()
        self._feat_dir_norm_mel_mod = self.get_normalized_feat_dir_mel_mod()
        create_folder(self._feat_dir_norm_mel_mod)
        
        for file_cnt, file_name in enumerate(os.listdir(self._feat_dir1)):
            print('{}: {}'.format(file_cnt, file_name))
            feat_file1 = np.load(os.path.join(self._feat_dir_norm1, file_name))
            feat_file2 = np.load(os.path.join(self._feat_dir_norm2, file_name))
            feat_file = np.concatenate((feat_file1, feat_file2), axis=-1)
            np.save(
                os.path.join(self._feat_dir_norm_mel_mod, file_name),
                feat_file
            )
            del feat_file

        #print('normalized files written to {}'.format(self._feat_dir_norm))
# ------------------------------- EXTRACT LABELS AND PREPROCESS IT -------------------------------
    def extract_all_labels(self):
        self._label_dir = self.get_label_dir()

        print('Extracting labels:')
        print('\t\taud_dir {}\n\t\tdesc_dir {}\n\t\tlabel_dir {}'.format(
            self._aud_dir, self._desc_dir, self._label_dir))
        create_folder(self._label_dir)
        for split in os.listdir(self._desc_dir):
            print('Split: {}'.format(split))
            for file_cnt, file_name in enumerate(os.listdir(os.path.join(self._desc_dir, split))):
                wav_filename = '{}.wav'.format(file_name.split('.')[0])
                desc_file_polar = self.load_output_format_file(os.path.join(self._desc_dir, split, file_name))
                desc_file = self.convert_output_format_polar_to_cartesian(desc_file_polar)
                label_mat = self.get_labels_for_file(desc_file)
                print('\t{}: {}, {}'.format(file_cnt, file_name, label_mat.shape))
                print('label',label_mat)
                np.save(os.path.join(self._label_dir, '{}.npy'.format(wav_filename.split('.')[0])), label_mat)

    
    

# -------------------------------  DCASE OUTPUT  FORMAT FUNCTIONS -------------------------------
    def load_output_format_file(self, _output_format_file):
        """
        Loads DCASE output format csv file and returns it in dictionary format

        :param _output_format_file: DCASE output format CSV
        :return: _output_dict: dictionary
        """
        _output_dict = {}
        _fid = open(_output_format_file, 'r')
        # next(_fid)
        for _line in _fid:
            _words = _line.strip().split(',')
            _frame_ind = int(_words[0])
            if _frame_ind not in _output_dict:
                _output_dict[_frame_ind] = []
            if len(_words) == 5: #read polar coordinates format, we ignore the track count 
                _output_dict[_frame_ind].append([int(_words[1]), float(_words[3]), float(_words[4]), int(_words[2])])
            elif len(_words) == 6: # read Cartesian coordinates format, we ignore the track count
                _output_dict[_frame_ind].append([int(_words[1]), float(_words[3]), float(_words[4]), float(_words[5]), int(_words[2])])
        _fid.close()
        return _output_dict

    def write_output_format_file(self, _output_format_file, _output_format_dict):
        """
        Writes DCASE output format csv file, given output format dictionary

        :param _output_format_file:
        :param _output_format_dict:
        :return:
        """
        _fid = open(_output_format_file, 'w')
        # _fid.write('{},{},{},{}\n'.format('frame number with 20ms hop (int)', 'class index (int)', 'azimuth angle (int)', 'elevation angle (int)'))
        for _frame_ind in _output_format_dict.keys():
            for _value in _output_format_dict[_frame_ind]:
                # Write Cartesian format output. Since baseline does not estimate track count we use a fixed value.
                _fid.write('{},{},{},{},{},{}\n'.format(int(_frame_ind), int(_value[0]), 0, float(_value[1]), float(_value[2]), float(_value[3])))
        _fid.close()

    def segment_labels(self, _pred_dict, _max_frames):
        '''
            Collects class-wise sound event location information in segments of length 1s from reference dataset
        :param _pred_dict: Dictionary containing frame-wise sound event time and location information. Output of SELD method
        :param _max_frames: Total number of frames in the recording
        :return: Dictionary containing class-wise sound event location information in each segment of audio
                dictionary_name[segment-index][class-index] = list(frame-cnt-within-segment, azimuth, elevation)
        '''
        nb_blocks = int(np.ceil(_max_frames/float(self._nb_label_frames_1s)))
        output_dict = {x: {} for x in range(nb_blocks)}
        for frame_cnt in range(0, _max_frames, self._nb_label_frames_1s):

            # Collect class-wise information for each block
            # [class][frame] = <list of doa values>
            # Data structure supports multi-instance occurence of same class
            block_cnt = frame_cnt // self._nb_label_frames_1s
            loc_dict = {}
            for audio_frame in range(frame_cnt, frame_cnt+self._nb_label_frames_1s):
                if audio_frame not in _pred_dict:
                    continue
                for value in _pred_dict[audio_frame]:
                    if value[0] not in loc_dict:
                        loc_dict[value[0]] = {}

                    block_frame = audio_frame - frame_cnt
                    if block_frame not in loc_dict[value[0]]:
                        loc_dict[value[0]][block_frame] = []
                    loc_dict[value[0]][block_frame].append(value[1:])

            # Update the block wise details collected above in a global structure
            for class_cnt in loc_dict:
                if class_cnt not in output_dict[block_cnt]:
                    output_dict[block_cnt][class_cnt] = []

                keys = [k for k in loc_dict[class_cnt]]
                values = [loc_dict[class_cnt][k] for k in loc_dict[class_cnt]]

                output_dict[block_cnt][class_cnt].append([keys, values])

        return output_dict

    def regression_label_format_to_output_format(self, _sed_labels, _doa_labels):
        """
        Converts the sed (classification) and doa labels predicted in regression format to dcase output format.

        :param _sed_labels: SED labels matrix [nb_frames, nb_classes]
        :param _doa_labels: DOA labels matrix [nb_frames, 2*nb_classes] or [nb_frames, 3*nb_classes]
        :return: _output_dict: returns a dict containing dcase output format
        """

        _nb_classes = len(self._unique_classes)
        _is_polar = _doa_labels.shape[-1] == 2*_nb_classes
        _azi_labels, _ele_labels = None, None
        _x, _y, _z = None, None, None
        if _is_polar:
            _azi_labels = _doa_labels[:, :_nb_classes]
            _ele_labels = _doa_labels[:, _nb_classes:]
        else:
            _x = _doa_labels[:, :_nb_classes]
            _y = _doa_labels[:, _nb_classes:2*_nb_classes]
            _z = _doa_labels[:, 2*_nb_classes:]

        _output_dict = {}
        for _frame_ind in range(_sed_labels.shape[0]):
            _tmp_ind = np.where(_sed_labels[_frame_ind, :])
            if len(_tmp_ind[0]):
                _output_dict[_frame_ind] = []
                for _tmp_class in _tmp_ind[0]:
                    if _is_polar:
                        _output_dict[_frame_ind].append([_tmp_class, _azi_labels[_frame_ind, _tmp_class], _ele_labels[_frame_ind, _tmp_class]])
                    else:
                        _output_dict[_frame_ind].append([_tmp_class, _x[_frame_ind, _tmp_class], _y[_frame_ind, _tmp_class], _z[_frame_ind, _tmp_class]])
        return _output_dict

    def convert_output_format_polar_to_cartesian(self, in_dict):
        out_dict = {}
        for frame_cnt in in_dict.keys():
            if frame_cnt not in out_dict:
                out_dict[frame_cnt] = []
                for tmp_val in in_dict[frame_cnt]:

                    ele_rad = tmp_val[2]*np.pi/180.
                    azi_rad = tmp_val[1]*np.pi/180

                    tmp_label = np.cos(ele_rad)
                    x = np.cos(azi_rad) * tmp_label
                    y = np.sin(azi_rad) * tmp_label
                    z = np.sin(ele_rad)
                    out_dict[frame_cnt].append([tmp_val[0], x, y, z, tmp_val[-1]])
        return out_dict

    def convert_output_format_cartesian_to_polar(self, in_dict):
        out_dict = {}
        for frame_cnt in in_dict.keys():
            if frame_cnt not in out_dict:
                out_dict[frame_cnt] = []
                for tmp_val in in_dict[frame_cnt]:
                    x, y, z = tmp_val[1], tmp_val[2], tmp_val[3]

                    # in degrees
                    azimuth = np.arctan2(y, x) * 180 / np.pi
                    elevation = np.arctan2(z, np.sqrt(x**2 + y**2)) * 180 / np.pi
                    r = np.sqrt(x**2 + y**2 + z**2)
                    out_dict[frame_cnt].append([tmp_val[0], azimuth, elevation, tmp_val[-1]])
        return out_dict

    # ------------------------------- Misc public functions -------------------------------
    def get_classes(self):
        return self._unique_classes

    def get_normalized_feat_dir1(self):
        return os.path.join(
            self._feat_label_dir,
            '{}_mel_norm'.format(self._dataset_combination)
        )
    def get_normalized_feat_dir2(self):
        return os.path.join(
            self._feat_label_dir,
            '{}_mod_norm'.format(self._dataset_combination)
        )
    def get_unnormalized_feat_dir1(self):
        return os.path.join(
            self._feat_label_dir,
            '{}_mel'.format(self._dataset_combination)
        )
    def get_normalized_feat_dir_mel_mod(self):
        return os.path.join(
            self._feat_label_dir,
            '{}_mel_mod_norm'.format(self._dataset_combination)
        )
    def get_unnormalized_feat_dir2(self):
        return os.path.join(
            self._feat_label_dir,
            '{}_mod'.format(self._dataset_combination)
        )
    def get_label_dir(self):
        if self._is_eval:
            return None
        else:
            return os.path.join(
                self._feat_label_dir, '{}_label'.format(self._dataset_combination)
            )

    def get_normalized_wts_file1(self):
        return os.path.join(
            self._feat_label_dir,
            '{}_mel_wts'.format(self._dataset)
        )
    def get_normalized_wts_file2(self):
        return os.path.join(
            self._feat_label_dir,
            '{}_mod_wts'.format(self._dataset)
        )
    def get_nb_channels(self):
        return self._nb_channels

    def get_nb_classes(self):
        return len(self._unique_classes)

    def nb_frames_1s(self):
        return self._nb_label_frames_1s

    def get_hop_len_sec(self):
        return self._hop_len_s

    def get_nb_frames(self):
        return self._max_label_frames

    def get_nb_mel_bins1(self):
        return self._nb_mel_bins1

    def get_nb_mel_bins2(self):
        return self._nb_mel_bins2


    def get_nb_mel_bins(self):
        return self._nb_mel_bins
def create_folder(folder_name):
    os.makedirs(folder_name, exist_ok=True)

def delete_and_create_folder(folder_name):
    if os.path.exists(folder_name) and os.path.isdir(folder_name):
        shutil.rmtree(folder_name)
    os.makedirs(folder_name, exist_ok=True)
