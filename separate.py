from __future__ import annotations
from typing import TYPE_CHECKING
from demucs.apply import apply_model, demucs_segments
from demucs.hdemucs import HDemucs
from demucs.model_v2 import auto_load_demucs_model_v2
from demucs.pretrained import get_model as _gm
from demucs.utils import apply_model_v1
from demucs.utils import apply_model_v2
from lib_v5.tfc_tdf_v3 import TFC_TDF_net, STFT
from lib_v5 import spec_utils
from lib_v5.vr_network import nets
from lib_v5.vr_network import nets_new
from lib_v5.vr_network.model_param_init import ModelParameters
from pathlib import Path
from gui_data.constants import *
from gui_data.error_handling import *
from scipy import signal
import audioread
import gzip
import librosa
import math
import numpy as np
import onnxruntime as ort
import os
import torch
import warnings
import pydub
import soundfile as sf
import traceback
import lib_v5.mdxnet as MdxnetSet
import math
#import random
from tqdm import tqdm
from onnx import load
from onnx2pytorch import ConvertModel

if TYPE_CHECKING:
    from UVR import ModelData

warnings.filterwarnings("ignore")
cpu = torch.device('cpu')

class SeperateAttributes:
    def __init__(self, model_data: ModelData, process_data: dict, main_model_primary_stem_4_stem=None, main_process_method=None):
        
        self.list_all_models: list
        self.process_data = process_data
        self.progress_value = 0
        self.set_progress_bar = process_data['set_progress_bar']
        self.write_to_console = process_data['write_to_console']
        self.audio_file = process_data['audio_file']
        self.audio_file_base = process_data['audio_file_base']
        self.export_path = process_data['export_path']
        self.cached_source_callback = process_data['cached_source_callback']
        self.cached_model_source_holder = process_data['cached_model_source_holder']
        self.is_4_stem_ensemble = process_data['is_4_stem_ensemble']
        self.list_all_models = process_data['list_all_models']
        self.process_iteration = process_data['process_iteration']
        self.is_pitch_change = model_data.is_pitch_change
        self.semitone_shift = model_data.semitone_shift
        self.is_match_frequency_pitch = model_data.is_match_frequency_pitch
        self.overlap = model_data.overlap
        self.overlap_mdx = model_data.overlap_mdx
        self.overlap_mdx23 = model_data.overlap_mdx23
        self.is_mdx_combine_stems = model_data.is_mdx_combine_stems
        self.is_mdx_c = model_data.is_mdx_c
        self.mdx_c_configs = model_data.mdx_c_configs
        self.mdxnet_stem_select = model_data.mdxnet_stem_select
        self.mixer_path = model_data.mixer_path
        self.model_samplerate = model_data.model_samplerate
        self.model_capacity = model_data.model_capacity
        self.is_vr_51_model = model_data.is_vr_51_model
        self.is_pre_proc_model = model_data.is_pre_proc_model
        self.is_secondary_model_activated = model_data.is_secondary_model_activated if not self.is_pre_proc_model else False
        self.is_secondary_model = model_data.is_secondary_model if not self.is_pre_proc_model else True
        self.process_method = model_data.process_method
        self.model_path = model_data.model_path
        self.model_name = model_data.model_name
        self.model_basename = model_data.model_basename
        self.wav_type_set = model_data.wav_type_set
        self.mp3_bit_set = model_data.mp3_bit_set
        self.save_format = model_data.save_format
        self.is_gpu_conversion = model_data.is_gpu_conversion
        self.is_normalization = model_data.is_normalization
        self.is_primary_stem_only = model_data.is_primary_stem_only if not self.is_secondary_model else model_data.is_primary_model_primary_stem_only
        self.is_secondary_stem_only = model_data.is_secondary_stem_only if not self.is_secondary_model else model_data.is_primary_model_secondary_stem_only      
        self.is_ensemble_mode = model_data.is_ensemble_mode
        self.secondary_model = model_data.secondary_model #
        self.primary_model_primary_stem = model_data.primary_model_primary_stem
        self.primary_stem_native = model_data.primary_stem_native
        self.primary_stem = model_data.primary_stem #
        self.secondary_stem = model_data.secondary_stem #
        self.is_invert_spec = model_data.is_invert_spec #
        self.is_deverb_vocals = model_data.is_deverb_vocals
        self.is_mixer_mode = model_data.is_mixer_mode #
        self.secondary_model_scale = model_data.secondary_model_scale #
        self.is_demucs_pre_proc_model_inst_mix = model_data.is_demucs_pre_proc_model_inst_mix #
        self.primary_source_map = {}
        self.secondary_source_map = {}
        self.primary_source = None
        self.secondary_source = None
        self.secondary_source_primary = None
        self.secondary_source_secondary = None
        self.main_model_primary_stem_4_stem = main_model_primary_stem_4_stem
        self.ensemble_primary_stem = model_data.ensemble_primary_stem
        self.is_gpu = False
        self.is_deverb = True

        if not model_data.process_method == DEMUCS_ARCH_TYPE:
            self.check_label_secondary_stem_runs()

            if self.is_pre_proc_model:
                self.is_primary_stem_only = True if self.primary_stem == INST_STEM else False
                self.is_secondary_stem_only = True if self.secondary_stem == INST_STEM else False

        if model_data.process_method == MDX_ARCH_TYPE:
            self.is_mdx_ckpt = model_data.is_mdx_ckpt
            self.primary_model_name, self.primary_sources = self.cached_source_callback(MDX_ARCH_TYPE, model_name=self.model_basename)
            self.is_denoise = model_data.is_denoise#
            self.is_mdx_c_seg_def = model_data.is_mdx_c_seg_def#
            self.mdx_batch_size = model_data.mdx_batch_size
            self.compensate = model_data.compensate
            self.mdx_window_size = model_data.mdx_window_size
            if not self.is_mdx_c:
                self.dim_f, self.dim_t = model_data.mdx_dim_f_set, 2**model_data.mdx_dim_t_set
            else:
                if not self.is_4_stem_ensemble:
                    self.primary_stem = model_data.ensemble_primary_stem if process_data['is_ensemble_master'] else model_data.primary_stem
                    self.secondary_stem = model_data.ensemble_secondary_stem if process_data['is_ensemble_master'] else model_data.secondary_stem
                self.check_label_secondary_stem_runs()
            self.n_fft = model_data.mdx_n_fft_scale_set
            self.chunks = model_data.chunks
            self.margin = model_data.margin
            self.adjust = 1
            self.dim_c = 4
            self.hop = 1024

            if self.is_gpu_conversion >= 0 and torch.cuda.is_available():
                self.is_gpu = True
                self.device, self.run_type = torch.device('cuda:0'), ['CUDAExecutionProvider']
            else:
                self.is_gpu = False
                self.device, self.run_type = torch.device('cpu'), ['CPUExecutionProvider']

        if model_data.process_method == DEMUCS_ARCH_TYPE:
            self.demucs_stems = model_data.demucs_stems if not main_process_method in [MDX_ARCH_TYPE, VR_ARCH_TYPE] else None
            self.secondary_model_4_stem = model_data.secondary_model_4_stem
            self.secondary_model_4_stem_scale = model_data.secondary_model_4_stem_scale
            self.primary_stem = model_data.ensemble_primary_stem if process_data['is_ensemble_master'] else model_data.primary_stem
            self.secondary_stem = model_data.ensemble_secondary_stem if process_data['is_ensemble_master'] else model_data.secondary_stem
            self.is_chunk_demucs = model_data.is_chunk_demucs
            self.segment = model_data.segment
            self.demucs_version = model_data.demucs_version
            self.demucs_source_list = model_data.demucs_source_list
            self.demucs_source_map = model_data.demucs_source_map
            self.is_demucs_combine_stems = model_data.is_demucs_combine_stems
            self.demucs_stem_count = model_data.demucs_stem_count
            self.pre_proc_model = model_data.pre_proc_model
            
            if self.is_secondary_model and not process_data['is_ensemble_master']:
                if not self.demucs_stem_count == 2 and model_data.primary_model_primary_stem == INST_STEM:
                    self.primary_stem = VOCAL_STEM
                    self.secondary_stem = INST_STEM
                else:
                    self.primary_stem = model_data.primary_model_primary_stem
                    self.secondary_stem = STEM_PAIR_MAPPER[self.primary_stem]
            
            if self.is_chunk_demucs:
                self.chunks_demucs = model_data.chunks_demucs
                self.margin_demucs = model_data.margin_demucs
            else:
                self.chunks_demucs = 0
                self.margin_demucs = 44100
                
            self.shifts = model_data.shifts
            self.is_split_mode = model_data.is_split_mode if not self.demucs_version == DEMUCS_V4 else True
            self.primary_model_name, self.primary_sources = self.cached_source_callback(DEMUCS_ARCH_TYPE, model_name=self.model_basename)

        if model_data.process_method == VR_ARCH_TYPE:
            self.primary_model_name, self.primary_sources = self.cached_source_callback(VR_ARCH_TYPE, model_name=self.model_basename)
            self.mp = model_data.vr_model_param
            self.high_end_process = model_data.is_high_end_process
            self.is_tta = model_data.is_tta
            self.is_post_process = model_data.is_post_process
            self.is_gpu_conversion = model_data.is_gpu_conversion
            self.batch_size = model_data.batch_size
            self.window_size = model_data.window_size
            self.input_high_end_h = None
            self.post_process_threshold = model_data.post_process_threshold
            self.aggressiveness = {'value': model_data.aggression_setting, 
                                   'split_bin': self.mp.param['band'][1]['crop_stop'], 
                                   'aggr_correction': self.mp.param.get('aggr_correction')}
            
    def check_label_secondary_stem_runs(self):
        
        if self.process_data['is_ensemble_master'] and not self.is_4_stem_ensemble:
            if not self.ensemble_primary_stem == self.primary_stem:
                self.is_primary_stem_only, self.is_secondary_stem_only = self.is_secondary_stem_only, self.is_primary_stem_only
        
        if self.is_secondary_model and not self.process_data['is_ensemble_master']:
            if not self.primary_model_primary_stem == self.primary_stem and not self.main_model_primary_stem_4_stem:
                self.is_primary_stem_only, self.is_secondary_stem_only = self.is_secondary_stem_only, self.is_primary_stem_only
                
        if self.main_model_primary_stem_4_stem:
            self.is_primary_stem_only = True if self.main_model_primary_stem_4_stem == self.primary_stem else False
            self.is_secondary_stem_only = True if not self.main_model_primary_stem_4_stem == self.primary_stem else False
            
    def start_inference_console_write(self):
        
        if self.is_secondary_model and not self.is_pre_proc_model:
            self.write_to_console(INFERENCE_STEP_2_SEC(self.process_method, self.model_basename))
        
        if self.is_pre_proc_model:
            self.write_to_console(INFERENCE_STEP_2_PRE(self.process_method, self.model_basename))
        
    def running_inference_console_write(self, is_no_write=False):
        
        self.write_to_console(DONE, base_text='') if not is_no_write else None
        self.set_progress_bar(0.05) if not is_no_write else None
        
        if self.is_secondary_model and not self.is_pre_proc_model:
            self.write_to_console(INFERENCE_STEP_1_SEC)
        elif self.is_pre_proc_model:
            self.write_to_console(INFERENCE_STEP_1_PRE)
        else:
            self.write_to_console(INFERENCE_STEP_1)
        
    def running_inference_progress_bar(self, length, is_match_mix=False):
        if not is_match_mix:
            self.progress_value += 1

            if (0.8/length*self.progress_value) >= 0.8:
                length = self.progress_value + 1
  
            self.set_progress_bar(0.1, (0.8/length*self.progress_value))
        
    def load_cached_sources(self, is_4_stem_demucs=False):
        
        if self.is_secondary_model and not self.is_pre_proc_model:
            self.write_to_console(INFERENCE_STEP_2_SEC_CACHED_MODOEL(self.process_method, self.model_basename))
        elif self.is_pre_proc_model:
            self.write_to_console(INFERENCE_STEP_2_PRE_CACHED_MODOEL(self.process_method, self.model_basename))
        else:
            self.write_to_console(INFERENCE_STEP_2_PRIMARY_CACHED)

        if not is_4_stem_demucs:
            primary_stem, secondary_stem = gather_sources(self.primary_stem, self.secondary_stem, self.primary_sources)
            
            return primary_stem, secondary_stem
            
    def cache_source(self, secondary_sources):
        
        model_occurrences = self.list_all_models.count(self.model_basename)
        
        if not model_occurrences <= 1:
            if self.process_method == MDX_ARCH_TYPE:
                self.cached_model_source_holder(MDX_ARCH_TYPE, secondary_sources, self.model_basename)
                
            if self.process_method == VR_ARCH_TYPE:
                self.cached_model_source_holder(VR_ARCH_TYPE, secondary_sources, self.model_basename)

            if self.process_method == DEMUCS_ARCH_TYPE:
                self.cached_model_source_holder(DEMUCS_ARCH_TYPE, secondary_sources, self.model_basename)
                
    def write_audio(self, stem_path, stem_source, samplerate, secondary_model_source=None, model_scale=None, stem_name=None):
                
        if not self.is_secondary_model:
            if self.is_secondary_model_activated:
                if isinstance(secondary_model_source, np.ndarray):
                    secondary_model_scale = model_scale if model_scale else self.secondary_model_scale
                    stem_source = spec_utils.average_dual_sources(stem_source, secondary_model_source, secondary_model_scale)
            
            if stem_name == VOCAL_STEM and self.is_deverb_vocals:
                stem_source = vr_denoiser(stem_source, self.device, is_deverber=True)
            
            sf.write(stem_path, stem_source, samplerate, subtype=self.wav_type_set)
            save_format(stem_path, self.save_format, self.mp3_bit_set) if not self.is_ensemble_mode else None
            
            self.write_to_console(DONE, base_text='')
            self.set_progress_bar(0.95)

    def run_mixer(self, mix, sources):
        try:
            if self.is_mixer_mode and len(sources) == 4:
                mixer = MdxnetSet.Mixer(self.device, self.mixer_path).eval()
                with torch.no_grad():
                    mix = torch.tensor(mix, dtype=torch.float32)
                    sources_ = torch.tensor(sources).detach()
                    x = torch.cat([sources_, mix.unsqueeze(0)], 0)
                    sources_ = mixer(x)
                final_source = np.array(sources_)
            else:
                final_source = sources
        except Exception as e:
            error_name = f'{type(e).__name__}'
            traceback_text = ''.join(traceback.format_tb(e.__traceback__))
            message = f'{error_name}: "{e}"\n{traceback_text}"'
            #print('Mixer Failed: ', message)
            final_source = sources
            
        return final_source

    def pitch_fix(self, source, sr_pitched, org_mix, is_demucs=False):
        semitone_shift = self.semitone_shift
        source = spec_utils.change_pitch_semitones(source, sr_pitched, semitone_shift=semitone_shift)[0]
        source = spec_utils.match_array_shapes(source, org_mix)
        return source
    
    def match_frequency_pitch(self, mix, is_demucs=False):
        source = mix
        if self.is_match_frequency_pitch and self.is_pitch_change:
            source, sr_pitched = spec_utils.change_pitch_semitones(mix, 44100, semitone_shift=-self.semitone_shift)
            source = self.pitch_fix(source, sr_pitched, mix, is_demucs=is_demucs)

        return source

class SeperateMDX(SeperateAttributes):        

    def seperate(self):
        samplerate = 44100

        if self.primary_model_name == self.model_basename and self.primary_sources:
            self.primary_source, self.secondary_source = self.load_cached_sources()
        else:
            self.start_inference_console_write()

            if self.is_mdx_ckpt:
                model_params = torch.load(self.model_path, map_location=lambda storage, loc: storage)['hyper_parameters']
                self.dim_c, self.hop = model_params['dim_c'], model_params['hop_length']
                separator = MdxnetSet.ConvTDFNet(**model_params)
                self.model_run = separator.load_from_checkpoint(self.model_path).to(self.device).eval()
            else:
                if self.mdx_window_size == self.dim_t:
                    ort_ = ort.InferenceSession(self.model_path, providers=self.run_type)
                    self.model_run = lambda spek:ort_.run(None, {'input': spek.cpu().numpy()})[0]
                else:
                    self.model_run = ConvertModel(load(self.model_path))
                    self.model_run.to(self.device).eval()

            self.initialize_model_settings()
            self.running_inference_console_write()
            self.stft = STFT(self.n_fft, self.hop, self.dim_f)
            mdx_net_cut = True if self.primary_stem in MDX_NET_FREQ_CUT and self.is_match_frequency_pitch else False
            
            mix = prepare_mix(self.audio_file)
            source = self.demix(mix)
            
            self.write_to_console(DONE, base_text='')            

        if self.is_secondary_model_activated:
            if self.secondary_model:
                self.secondary_source_primary, self.secondary_source_secondary = process_secondary_model(self.secondary_model, self.process_data, main_process_method=self.process_method)
        
        if not self.is_secondary_stem_only:
            self.write_to_console(f'{SAVING_STEM[0]}{self.primary_stem}{SAVING_STEM[1]}') if not self.is_secondary_model else None
            primary_stem_path = os.path.join(self.export_path, f'{self.audio_file_base}_({self.primary_stem}).wav')
            if not isinstance(self.primary_source, np.ndarray):
                self.primary_source = spec_utils.normalize(source, self.is_normalization).T
            self.primary_source_map = {self.primary_stem: self.primary_source}
            self.write_audio(primary_stem_path, self.primary_source, samplerate, self.secondary_source_primary, stem_name=self.primary_stem)

        if not self.is_primary_stem_only:
            self.write_to_console(f'{SAVING_STEM[0]}{self.secondary_stem}{SAVING_STEM[1]}') if not self.is_secondary_model else None
            secondary_stem_path = os.path.join(self.export_path, f'{self.audio_file_base}_({self.secondary_stem}).wav')
            if not isinstance(self.secondary_source, np.ndarray):
                raw_mix = self.demix(self.match_frequency_pitch(mix), is_match_mix=True) if mdx_net_cut else self.match_frequency_pitch(mix)
                self.secondary_source, raw_mix = spec_utils.normalize_two_stem(source, raw_mix, self.is_normalization)
            
                if self.is_invert_spec:
                    self.secondary_source = spec_utils.invert_stem(raw_mix, self.secondary_source)
                else:
                    #print(self.secondary_source.shape, raw_mix.shape)
                    self.secondary_source = (-self.secondary_source.T+raw_mix.T)

            self.secondary_source_map = {self.secondary_stem: self.secondary_source}
            self.write_audio(secondary_stem_path, self.secondary_source, samplerate, self.secondary_source_secondary, stem_name=self.secondary_stem)

        torch.cuda.empty_cache()
        secondary_sources = {**self.primary_source_map, **self.secondary_source_map}

        self.cache_source(secondary_sources)

        if self.is_secondary_model:
            return secondary_sources

    def initialize_model_settings(self):
        self.n_bins = self.n_fft//2+1
        self.trim = self.n_fft//2
        self.chunk_size = self.hop * (self.mdx_window_size-1)
        self.gen_size = self.chunk_size-2*self.trim

    def demix(self, mix, is_match_mix=False):

        org_mix = mix
        tar_waves_ = []

        if is_match_mix:
            chunk_size = self.hop * (256-1)
            overlap = 0.02
        else:
            chunk_size = self.chunk_size
            overlap = self.overlap_mdx
            
            if self.is_pitch_change:
                mix, sr_pitched = spec_utils.change_pitch_semitones(mix, 44100, semitone_shift=-self.semitone_shift)

        gen_size = chunk_size-2*self.trim

        pad = gen_size + self.trim - ((mix.shape[-1]) % gen_size)
        mixture = np.concatenate((np.zeros((2, self.trim), dtype='float32'), mix, np.zeros((2, pad), dtype='float32')), 1)

        step = self.chunk_size - self.n_fft if overlap == DEFAULT else int((1 - overlap) * chunk_size)
        result = np.zeros((1, 2, mixture.shape[-1]), dtype=np.float32)
        divider = np.zeros((1, 2, mixture.shape[-1]), dtype=np.float32)
        total = 0
        total_chunks = (mixture.shape[-1] + step - 1) // step

        for i in range(0, mixture.shape[-1], step):
            total += 1
            start = i
            end = min(i + chunk_size, mixture.shape[-1])

            chunk_size_actual = end - start

            if overlap == 0:
                window = None
            else:
                window = np.hanning(chunk_size_actual)
                window = np.tile(window[None, None, :], (1, 2, 1))

            mix_part_ = mixture[:, start:end]
            if end != i + chunk_size:
                pad_size = (i + chunk_size) - end
                mix_part_ = np.concatenate((mix_part_, np.zeros((2, pad_size), dtype='float32')), axis=-1)

            mix_part = torch.tensor([mix_part_], dtype=torch.float32).to(self.device)
            mix_waves = mix_part.split(self.mdx_batch_size)

            with torch.no_grad():
                for mix_wave in mix_waves:
                    self.running_inference_progress_bar(total_chunks, is_match_mix=is_match_mix)

                    tar_waves = self.run_model(mix_wave, is_match_mix=is_match_mix)

                    if window is not None:
                        tar_waves[..., :chunk_size_actual] *= window 
                        divider[..., start:end] += window
                    else:
                        divider[..., start:end] += 1

                    result[..., start:end] += tar_waves[..., :end-start]

        tar_waves = result / divider
        tar_waves_.append(tar_waves)

        tar_waves_ = np.vstack(tar_waves_)[:, :, self.trim:-self.trim]
        tar_waves = np.concatenate(tar_waves_, axis=-1)[:, :mix.shape[-1]]
        
        source = tar_waves[:,0:None]

        if self.is_pitch_change and not is_match_mix:
            source = self.pitch_fix(source, sr_pitched, org_mix)

        source = source if is_match_mix else source*self.compensate

        if self.is_denoise and not is_match_mix:
            if NO_STEM in self.primary_stem_native or self.primary_stem_native == INST_STEM:
                source = org_mix - vr_denoiser(org_mix-source, self.device)
            else:
                source = vr_denoiser(source, self.device)

        return source

    def run_model(self, mix, is_match_mix=False):
        
        spek = self.stft(mix.to(self.device))*self.adjust
        spek[:, :, :3, :] *= 0 

        if is_match_mix:
            spec_pred = spek.cpu().numpy()
        else:
            spec_pred = -self.model_run(-spek)*0.5+self.model_run(spek)*0.5 if self.is_denoise else self.model_run(spek)
            #spec_pred = spek.cpu().numpy() - spec_pred*self.compensate

        return self.stft.inverse(torch.tensor(spec_pred).to(self.device)).cpu().detach().numpy()


class SeperateMDXC(SeperateAttributes):        

    def seperate(self):

        samplerate = 44100

        if self.primary_model_name == self.model_basename and self.primary_sources:
            self.primary_source, self.secondary_source = self.load_cached_sources()
        else:
            self.start_inference_console_write()
            self.running_inference_console_write()
            mix = prepare_mix(self.audio_file)
            
            sources = self.demix(mix)
            self.write_to_console(DONE, base_text='')            

        if self.is_secondary_model_activated:
            if self.secondary_model:
                self.secondary_source_primary, self.secondary_source_secondary = process_secondary_model(self.secondary_model, self.process_data, main_process_method=self.process_method)

        stem_list = [self.mdx_c_configs.training.target_instrument] if self.mdx_c_configs.training.target_instrument else [i for i in self.mdx_c_configs.training.instruments]
        
        if self.is_secondary_model:
            self.mdxnet_stem_select = self.main_model_primary_stem_4_stem if self.main_model_primary_stem_4_stem else self.primary_model_primary_stem
            self.primary_stem = self.mdxnet_stem_select
            self.secondary_stem = secondary_stem(self.mdxnet_stem_select)
            self.is_primary_stem_only, self.is_secondary_stem_only = False, False

        if (self.mdxnet_stem_select == ALL_STEMS and not self.process_data['is_ensemble_master'] and not len(stem_list) == 1 and not self.is_secondary_model) or self.is_4_stem_ensemble and not len(stem_list) == 1:
            for stem in stem_list:
                self.write_to_console(f'{SAVING_STEM[0]}{stem}{SAVING_STEM[1]}') if not self.is_secondary_model else None
                primary_stem_path = os.path.join(self.export_path, f'{self.audio_file_base}_({stem}).wav')
                self.primary_source = spec_utils.normalize(sources[stem], self.is_normalization).T
                self.primary_source_map = {self.primary_stem: self.primary_source}
                self.write_audio(primary_stem_path, self.primary_source, samplerate, self.secondary_source_primary, stem_name=stem)
        else:
            source_primary = sources if len(stem_list) == 1 else sources[self.mdxnet_stem_select]

            if not self.is_secondary_stem_only:
                self.write_to_console(f'{SAVING_STEM[0]}{self.primary_stem}{SAVING_STEM[1]}') if not self.is_secondary_model else None
                primary_stem_path = os.path.join(self.export_path, f'{self.audio_file_base}_({self.primary_stem}).wav')
                if not isinstance(self.primary_source, np.ndarray):
                    self.primary_source = spec_utils.normalize(source_primary, self.is_normalization).T

                self.primary_source_map = {self.primary_stem: self.primary_source}
                self.write_audio(primary_stem_path, self.primary_source, samplerate, self.secondary_source_primary, stem_name=self.primary_stem)

            if not self.is_primary_stem_only:
                self.write_to_console(f'{SAVING_STEM[0]}{self.secondary_stem}{SAVING_STEM[1]}') if not self.is_secondary_model else None
                secondary_stem_path = os.path.join(self.export_path, f'{self.audio_file_base}_({self.secondary_stem}).wav')
                if not isinstance(self.secondary_source, np.ndarray):
                    
                    if self.is_mdx_combine_stems and len(stem_list) >= 2:
                        if len(stem_list) == 2:
                            secondary_source = sources[self.secondary_stem]
                        else:
                            sources.pop(self.primary_stem)
                            next_stem = next(iter(sources))
                            secondary_source = np.zeros_like(sources[next_stem])
                            for v in sources.values():
                                secondary_source += v
                                
                        self.secondary_source = spec_utils.normalize(secondary_source, self.is_normalization).T 
                    else:
                        #raw_mix = self.demix(mix, is_match_mix=True)[0] if mdx_net_cut else raw_mix
                        self.secondary_source, raw_mix = spec_utils.normalize_two_stem(source_primary, self.match_frequency_pitch(mix), self.is_normalization)
                        self.secondary_source = spec_utils.to_shape(self.secondary_source, raw_mix.shape)
                    
                        if self.is_invert_spec:
                            self.secondary_source = spec_utils.invert_stem(raw_mix, self.secondary_source)
                        else:
                            self.secondary_source = (-self.secondary_source.T+raw_mix.T)
                            
                self.secondary_source_map = {self.secondary_stem: self.secondary_source}
                self.write_audio(secondary_stem_path, self.secondary_source, samplerate, self.secondary_source_secondary, stem_name=self.secondary_stem)

        torch.cuda.empty_cache()
        secondary_sources = {**self.primary_source_map, **self.secondary_source_map}

        self.cache_source(secondary_sources)

        if self.is_secondary_model:
            return secondary_sources

    def demix(self, mix):
        sr_pitched = 441000
        org_mix = mix
        if self.is_pitch_change:
            mix, sr_pitched = spec_utils.change_pitch_semitones(mix, 44100, semitone_shift=-self.semitone_shift)
        
        model = TFC_TDF_net(self.mdx_c_configs).eval().to(self.device)
        model.load_state_dict(torch.load(self.model_path, map_location=self.device))
        mix = torch.tensor(mix, dtype=torch.float32)

        try:
            S = model.num_target_instruments
        except Exception as e:
            S = model.module.num_target_instruments

        mdx_window_size = self.mdx_c_configs.inference.dim_t if self.is_mdx_c_seg_def else self.mdx_window_size
        
        batch_size = self.mdx_batch_size
        C = self.mdx_c_configs.audio.hop_length * (mdx_window_size - 1)
        N = self.overlap_mdx23

        H = C // N
        L = mix.shape[1]
        pad_size = H - (L - C) % H
        mix = torch.cat([torch.zeros(2, C - H), mix, torch.zeros(2, pad_size + C - H)], 1)
        mix = mix.to(self.device)

        chunks = []
        i = 0
        while i + C <= mix.shape[1]:
            chunks.append(mix[:, i:i + C])
            i += H
        chunks = torch.stack(chunks)

        batches = []
        i = 0
        while i < len(chunks):
            batches.append(chunks[i:i + batch_size])
            i = i + batch_size

        X = torch.zeros(S, 2, C - H) if S > 1 else torch.zeros(2, C - H)
        X = X.to(self.device)

        #with torch.cuda.amp.autocast():
        with torch.no_grad():
            for batch in batches:
                self.running_inference_progress_bar(len(batches))
                x = model(batch)
                for w in x:
                    a = X[..., :-(C - H)]
                    b = X[..., -(C - H):] + w[..., :(C - H)]
                    c = w[..., (C - H):]
                    X = torch.cat([a, b, c], -1)

        estimated_sources = X[..., C - H:-(pad_size + C - H)] / N

        pitch_fix = lambda s:self.pitch_fix(s, sr_pitched, org_mix)

        if S > 1:
            sources = {k: pitch_fix(v) if self.is_pitch_change else v for k, v in zip(self.mdx_c_configs.training.instruments, estimated_sources.cpu().detach().numpy())}
            
            if self.is_denoise:
                if VOCAL_STEM in sources.keys() and INST_STEM in sources.keys():
                    sources[VOCAL_STEM] = vr_denoiser(sources[VOCAL_STEM], self.device)
                    sources[INST_STEM] = org_mix - sources[VOCAL_STEM]
                            
            return sources
        else:
            est_s = estimated_sources.cpu().detach().numpy()
            return pitch_fix(est_s) if self.is_pitch_change else est_s

class SeperateDemucs(SeperateAttributes):        

    def seperate(self):
        samplerate = 44100
        source = None
        model_scale = None
        stem_source = None
        stem_source_secondary = None
        inst_mix = None
        inst_source = None
        is_no_write = False
        is_no_piano_guitar = False

        if self.primary_model_name == self.model_basename and type(self.primary_sources) is dict and not self.pre_proc_model:
            self.primary_source, self.secondary_source = self.load_cached_sources()
        elif self.primary_model_name == self.model_basename and isinstance(self.primary_sources, np.ndarray) and not self.pre_proc_model:
            source = self.primary_sources
            self.load_cached_sources(is_4_stem_demucs=True)
        else:
            self.start_inference_console_write()

            if self.is_gpu_conversion >= 0:
                self.device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu') 
            else:
                self.device = torch.device('cpu')
            
            if self.demucs_version == DEMUCS_V1:
                if str(self.model_path).endswith(".gz"):
                    self.model_path = gzip.open(self.model_path, "rb")
                klass, args, kwargs, state = torch.load(self.model_path)
                self.demucs = klass(*args, **kwargs)
                self.demucs.to(self.device) 
                self.demucs.load_state_dict(state)
            elif self.demucs_version == DEMUCS_V2:
                self.demucs = auto_load_demucs_model_v2(self.demucs_source_list, self.model_path)
                self.demucs.to(self.device) 
                self.demucs.load_state_dict(torch.load(self.model_path))
                self.demucs.eval()
            else:  
                self.demucs = HDemucs(sources=self.demucs_source_list)
                self.demucs = _gm(name=os.path.splitext(os.path.basename(self.model_path))[0], 
                                  repo=Path(os.path.dirname(self.model_path)))
                self.demucs = demucs_segments(self.segment, self.demucs)
                self.demucs.to(self.device)
                self.demucs.eval()

            if self.pre_proc_model:
                if self.primary_stem not in [VOCAL_STEM, INST_STEM]:
                    is_no_write = True
                    self.write_to_console(DONE, base_text='')
                    mix_no_voc = process_secondary_model(self.pre_proc_model, self.process_data, is_pre_proc_model=True)
                    inst_mix = prepare_mix(mix_no_voc[INST_STEM])
                    self.process_iteration()
                    self.running_inference_console_write(is_no_write=is_no_write)
                    inst_source = self.demix_demucs(inst_mix)
                    inst_source = self.run_mixer(inst_mix, inst_source)
                    self.process_iteration()

            self.running_inference_console_write(is_no_write=is_no_write) if not self.pre_proc_model else None
            mix = prepare_mix(self.audio_file)
            
            if self.primary_model_name == self.model_basename and isinstance(self.primary_sources, np.ndarray) and self.pre_proc_model:
                source = self.primary_sources
            else:
                source = self.demix_demucs(mix)
                source = self.run_mixer(mix, source)
            
            self.write_to_console(DONE, base_text='')
            
            del self.demucs
            torch.cuda.empty_cache()
            
        if isinstance(inst_source, np.ndarray):
            source_reshape = spec_utils.reshape_sources(inst_source[self.demucs_source_map[VOCAL_STEM]], source[self.demucs_source_map[VOCAL_STEM]])
            inst_source[self.demucs_source_map[VOCAL_STEM]] = source_reshape
            source = inst_source

        if isinstance(source, np.ndarray):
            if len(source) == 2:
                self.demucs_source_map = DEMUCS_2_SOURCE_MAPPER
            else:
                self.demucs_source_map = DEMUCS_6_SOURCE_MAPPER if len(source) == 6 else DEMUCS_4_SOURCE_MAPPER

                if len(source) == 6 and self.process_data['is_ensemble_master'] or len(source) == 6 and self.is_secondary_model:
                    is_no_piano_guitar = True
                    six_stem_other_source = list(source)
                    six_stem_other_source = [i for n, i in enumerate(source) if n in [self.demucs_source_map[OTHER_STEM], self.demucs_source_map[GUITAR_STEM], self.demucs_source_map[PIANO_STEM]]]
                    other_source = np.zeros_like(six_stem_other_source[0])
                    for i in six_stem_other_source:
                        other_source += i
                    source_reshape = spec_utils.reshape_sources(source[self.demucs_source_map[OTHER_STEM]], other_source)
                    source[self.demucs_source_map[OTHER_STEM]] = source_reshape

        if (self.demucs_stems == ALL_STEMS and not self.process_data['is_ensemble_master']) or self.is_4_stem_ensemble:
            self.cache_source(source)
            
            for stem_name, stem_value in self.demucs_source_map.items():
                if self.is_secondary_model_activated and not self.is_secondary_model and not stem_value >= 4:
                    if self.secondary_model_4_stem[stem_value]:
                        model_scale = self.secondary_model_4_stem_scale[stem_value]
                        stem_source_secondary = process_secondary_model(self.secondary_model_4_stem[stem_value], self.process_data, main_model_primary_stem_4_stem=stem_name, is_4_stem_demucs=True)
                        print(stem_source_secondary)
                        if isinstance(stem_source_secondary, np.ndarray):
                            stem_source_secondary = stem_source_secondary[1 if self.secondary_model_4_stem[stem_value].demucs_stem_count == 2 else stem_value]
                            stem_source_secondary = spec_utils.normalize(stem_source_secondary, self.is_normalization).T
                        elif type(stem_source_secondary) is dict:
                            stem_source_secondary = stem_source_secondary[stem_name]
                            
                stem_source_secondary = None if stem_value >= 4 else stem_source_secondary
                self.write_to_console(f'{SAVING_STEM[0]}{stem_name}{SAVING_STEM[1]}') if not self.is_secondary_model else None
                stem_path = os.path.join(self.export_path, f'{self.audio_file_base}_({stem_name}).wav')
                stem_source = spec_utils.normalize(source[stem_value], self.is_normalization).T
                self.write_audio(stem_path, stem_source, samplerate, secondary_model_source=stem_source_secondary, model_scale=model_scale)

            if self.is_secondary_model:    
                return source
        else:
            if self.is_secondary_model_activated:
                if self.secondary_model:
                    self.secondary_source_primary, self.secondary_source_secondary = process_secondary_model(self.secondary_model, self.process_data, main_process_method=self.process_method)

            if not self.is_secondary_stem_only:
                self.write_to_console(f'{SAVING_STEM[0]}{self.primary_stem}{SAVING_STEM[1]}') if not self.is_secondary_model else None
                primary_stem_path = os.path.join(self.export_path, f'{self.audio_file_base}_({self.primary_stem}).wav')
                if not isinstance(self.primary_source, np.ndarray):
                    self.primary_source = spec_utils.normalize(source[self.demucs_source_map[self.primary_stem]], self.is_normalization).T
                self.primary_source_map = {self.primary_stem: self.primary_source}
                self.write_audio(primary_stem_path, self.primary_source, samplerate, self.secondary_source_primary)

            if not self.is_primary_stem_only:
                def secondary_save(sec_stem_name, source, raw_mixture=None, is_inst_mixture=False):
                    secondary_source = self.secondary_source if not is_inst_mixture else None
                    self.write_to_console(f'{SAVING_STEM[0]}{sec_stem_name}{SAVING_STEM[1]}') if not self.is_secondary_model else None
                    secondary_stem_path = os.path.join(self.export_path, f'{self.audio_file_base}_({sec_stem_name}).wav')
                    secondary_source_secondary = None
                    
                    if not isinstance(secondary_source, np.ndarray):
                        if self.is_demucs_combine_stems:
                            source = list(source)
                            if is_inst_mixture:
                                source = [i for n, i in enumerate(source) if not n in [self.demucs_source_map[self.primary_stem], self.demucs_source_map[VOCAL_STEM]]]
                            else:
                                source.pop(self.demucs_source_map[self.primary_stem])
                                
                            source = source[:len(source) - 2] if is_no_piano_guitar else source
                            secondary_source = np.zeros_like(source[0])
                            for i in source:
                                secondary_source += i
                            secondary_source = spec_utils.normalize(secondary_source, self.is_normalization).T
                        else:
                            if not isinstance(raw_mixture, np.ndarray):
                                raw_mixture = prepare_mix(self.audio_file)
       
                            secondary_source, raw_mixture = spec_utils.normalize_two_stem(source[self.demucs_source_map[self.primary_stem]], raw_mixture, self.is_normalization)
                            
                            if self.is_invert_spec:
                                secondary_source = spec_utils.invert_stem(raw_mixture, secondary_source)
                            else:
                                raw_mixture = spec_utils.reshape_sources(secondary_source, raw_mixture)
                                secondary_source = (-secondary_source.T+raw_mixture.T)
                            
                    if not is_inst_mixture:
                        self.secondary_source = secondary_source
                        secondary_source_secondary = self.secondary_source_secondary
                        self.secondary_source_map = {self.secondary_stem: self.secondary_source}

                    self.write_audio(secondary_stem_path, secondary_source, samplerate, secondary_source_secondary)

                secondary_save(self.secondary_stem, source, raw_mixture=mix)
                
                if self.is_demucs_pre_proc_model_inst_mix and self.pre_proc_model and not self.is_4_stem_ensemble:
                    secondary_save(f"{self.secondary_stem} {INST_STEM}", source, raw_mixture=inst_mix, is_inst_mixture=True)

            secondary_sources = {**self.primary_source_map, **self.secondary_source_map}

            self.cache_source(secondary_sources)
            
            if self.is_secondary_model:    
                return secondary_sources
    
    def demix_demucs(self, mix):
        
        org_mix = mix
        
        if self.is_pitch_change:
            mix, sr_pitched = spec_utils.change_pitch_semitones(mix, 44100, semitone_shift=-self.semitone_shift)
        
        processed = {}
        mix = torch.tensor(mix, dtype=torch.float32)
        ref = mix.mean(0)        
        mix = (mix - ref.mean()) / ref.std()
        mix_infer = mix 
        
        with torch.no_grad():
            if self.demucs_version == DEMUCS_V1:
                sources = apply_model_v1(self.demucs, 
                                            mix_infer.to(self.device), 
                                            self.shifts, 
                                            self.is_split_mode,
                                            set_progress_bar=self.set_progress_bar)
            elif self.demucs_version == DEMUCS_V2:
                sources = apply_model_v2(self.demucs, 
                                            mix_infer.to(self.device), 
                                            self.shifts,
                                            self.is_split_mode,
                                            self.overlap,
                                            set_progress_bar=self.set_progress_bar)
            else:
                sources = apply_model(self.demucs, 
                                        mix_infer[None], 
                                        self.shifts,
                                        self.is_split_mode,
                                        self.overlap,
                                        static_shifts=1 if self.shifts == 0 else self.shifts,
                                        set_progress_bar=self.set_progress_bar,
                                        device=self.device)[0]
        
        sources = (sources * ref.std() + ref.mean()).cpu().numpy()
        sources[[0,1]] = sources[[1,0]]
        processed[mix] = sources[:,:,0:None].copy()
        sources = list(processed.values())
        sources = [s[:,:,0:None] for s in sources]
        #sources = [self.pitch_fix(s[:,:,0:None], sr_pitched, org_mix) if self.is_pitch_change else s[:,:,0:None] for s in sources]
        sources = np.concatenate(sources, axis=-1)
                     
        if self.is_pitch_change:
            sources = [self.pitch_fix(stem, sr_pitched, org_mix, is_demucs=True) for stem in sources]
                        
        return sources

class SeperateVR(SeperateAttributes):        

    def seperate(self):
        if self.primary_model_name == self.model_basename and self.primary_sources:
            self.primary_source, self.secondary_source = self.load_cached_sources()
        else:
            self.start_inference_console_write()
            if self.is_gpu_conversion >= 0:
                if OPERATING_SYSTEM == 'Darwin':
                    device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
                else:
                    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu') 
            else:
                device = torch.device('cpu')

            nn_arch_sizes = [
                31191, # default
                33966, 56817, 123821, 123812, 129605, 218409, 537238, 537227]
            vr_5_1_models = [56817, 218409]
            model_size = math.ceil(os.stat(self.model_path).st_size / 1024)
            nn_arch_size = min(nn_arch_sizes, key=lambda x:abs(x-model_size))

            if nn_arch_size in vr_5_1_models or self.is_vr_51_model:
                self.model_run = nets_new.CascadedNet(self.mp.param['bins'] * 2, 
                                                      nn_arch_size, 
                                                      nout=self.model_capacity[0], 
                                                      nout_lstm=self.model_capacity[1])
                print('51')
            else:
                self.model_run = nets.determine_model_capacity(self.mp.param['bins'] * 2, nn_arch_size)
                print('40')
                            
            self.model_run.load_state_dict(torch.load(self.model_path, map_location=cpu)) 
            self.model_run.to(device) 

            self.running_inference_console_write()
                        
            y_spec, v_spec = self.inference_vr(self.loading_mix(), device, self.aggressiveness)
            self.write_to_console(DONE, base_text='')
            
        if self.is_secondary_model_activated:
            if self.secondary_model:
                self.secondary_source_primary, self.secondary_source_secondary = process_secondary_model(self.secondary_model, self.process_data, main_process_method=self.process_method)

        if not self.is_secondary_stem_only:
            self.write_to_console(f'{SAVING_STEM[0]}{self.primary_stem}{SAVING_STEM[1]}') if not self.is_secondary_model else None
            primary_stem_path = os.path.join(self.export_path, f'{self.audio_file_base}_({self.primary_stem}).wav')
            if not isinstance(self.primary_source, np.ndarray):
                self.primary_source = spec_utils.normalize(self.spec_to_wav(y_spec), self.is_normalization).T
                if not self.model_samplerate == 44100:
                    self.primary_source = librosa.resample(self.primary_source.T, orig_sr=self.model_samplerate, target_sr=44100).T
                
            self.primary_source_map = {self.primary_stem: self.primary_source}
            
            self.write_audio(primary_stem_path, self.primary_source, 44100, self.secondary_source_primary)

        if not self.is_primary_stem_only:
            self.write_to_console(f'{SAVING_STEM[0]}{self.secondary_stem}{SAVING_STEM[1]}') if not self.is_secondary_model else None
            secondary_stem_path = os.path.join(self.export_path, f'{self.audio_file_base}_({self.secondary_stem}).wav')
            if not isinstance(self.secondary_source, np.ndarray):
                self.secondary_source = self.spec_to_wav(v_spec)
                self.secondary_source = spec_utils.normalize(self.spec_to_wav(v_spec), self.is_normalization).T
                if not self.model_samplerate == 44100:
                    self.secondary_source = librosa.resample(self.secondary_source.T, orig_sr=self.model_samplerate, target_sr=44100).T
            
            self.secondary_source_map = {self.secondary_stem: self.secondary_source}
            
            self.write_audio(secondary_stem_path, self.secondary_source, 44100, self.secondary_source_secondary)
            
        torch.cuda.empty_cache()
        secondary_sources = {**self.primary_source_map, **self.secondary_source_map}
        self.cache_source(secondary_sources)

        if self.is_secondary_model:
            return secondary_sources
            
    def loading_mix(self):

        X_wave, X_spec_s = {}, {}
        
        bands_n = len(self.mp.param['band'])
        
        for d in range(bands_n, 0, -1):        
            bp = self.mp.param['band'][d]
        
            if OPERATING_SYSTEM == 'Darwin':
                wav_resolution = 'polyphase' if SYSTEM_PROC == ARM or ARM in SYSTEM_ARCH else bp['res_type']
            else:
                wav_resolution = 'polyphase'#bp['res_type']
        
            if d == bands_n: # high-end band
                X_wave[d], _ = librosa.load(self.audio_file, bp['sr'], False, dtype=np.float32, res_type=wav_resolution)
                    
                if not np.any(X_wave[d]) and self.audio_file.endswith('.mp3'):
                    X_wave[d] = rerun_mp3(self.audio_file, bp['sr'])

                if X_wave[d].ndim == 1:
                    X_wave[d] = np.asarray([X_wave[d], X_wave[d]])
            else: # lower bands
                X_wave[d] = librosa.resample(X_wave[d+1], self.mp.param['band'][d+1]['sr'], bp['sr'], res_type=wav_resolution)
                
            X_spec_s[d] = spec_utils.wave_to_spectrogram_mt(X_wave[d], bp['hl'], bp['n_fft'], self.mp.param['mid_side'], 
                                                            self.mp.param['mid_side_b2'], self.mp.param['reverse'])
            
            if d == bands_n and self.high_end_process != 'none':
                self.input_high_end_h = (bp['n_fft']//2 - bp['crop_stop']) + (self.mp.param['pre_filter_stop'] - self.mp.param['pre_filter_start'])
                self.input_high_end = X_spec_s[d][:, bp['n_fft']//2-self.input_high_end_h:bp['n_fft']//2, :]

        X_spec = spec_utils.combine_spectrograms(X_spec_s, self.mp)
        
        del X_wave, X_spec_s

        return X_spec

    def inference_vr(self, X_spec, device, aggressiveness):
        def _execute(X_mag_pad, roi_size):
            X_dataset = []
            patches = (X_mag_pad.shape[2] - 2 * self.model_run.offset) // roi_size
            total_iterations = patches//self.batch_size if not self.is_tta else (patches//self.batch_size)*2
            for i in range(patches):
                start = i * roi_size
                X_mag_window = X_mag_pad[:, :, start:start + self.window_size]
                X_dataset.append(X_mag_window)

            X_dataset = np.asarray(X_dataset)
            self.model_run.eval()
            with torch.no_grad():
                mask = []
                for i in range(0, patches, self.batch_size):
                    self.progress_value += 1
                    if self.progress_value >= total_iterations:
                        self.progress_value = total_iterations
                    self.set_progress_bar(0.1, 0.8/total_iterations*self.progress_value)
                    X_batch = X_dataset[i: i + self.batch_size]
                    X_batch = torch.from_numpy(X_batch).to(device)
                    pred = self.model_run.predict_mask(X_batch)
                    if not pred.size()[3] > 0:
                        raise Exception(ERROR_MAPPER[WINDOW_SIZE_ERROR])
                    pred = pred.detach().cpu().numpy()
                    pred = np.concatenate(pred, axis=2)
                    mask.append(pred)
                if len(mask) == 0:
                    raise Exception(ERROR_MAPPER[WINDOW_SIZE_ERROR])
                
                mask = np.concatenate(mask, axis=2)
            return mask

        def postprocess(mask, X_mag, X_phase):
            is_non_accom_stem = False
            for stem in NON_ACCOM_STEMS:
                if stem == self.primary_stem:
                    is_non_accom_stem = True
                    
            mask = spec_utils.adjust_aggr(mask, is_non_accom_stem, aggressiveness)

            if self.is_post_process:
                mask = spec_utils.merge_artifacts(mask, thres=self.post_process_threshold)

            y_spec = mask * X_mag * np.exp(1.j * X_phase)
            v_spec = (1 - mask) * X_mag * np.exp(1.j * X_phase)
        
            return y_spec, v_spec
        
        X_mag, X_phase = spec_utils.preprocess(X_spec)
        n_frame = X_mag.shape[2]
        pad_l, pad_r, roi_size = spec_utils.make_padding(n_frame, self.window_size, self.model_run.offset)
        X_mag_pad = np.pad(X_mag, ((0, 0), (0, 0), (pad_l, pad_r)), mode='constant')
        X_mag_pad /= X_mag_pad.max()
        mask = _execute(X_mag_pad, roi_size)
        
        if self.is_tta:
            pad_l += roi_size // 2
            pad_r += roi_size // 2
            X_mag_pad = np.pad(X_mag, ((0, 0), (0, 0), (pad_l, pad_r)), mode='constant')
            X_mag_pad /= X_mag_pad.max()
            mask_tta = _execute(X_mag_pad, roi_size)
            mask_tta = mask_tta[:, :, roi_size // 2:]
            mask = (mask[:, :, :n_frame] + mask_tta[:, :, :n_frame]) * 0.5
        else:
            mask = mask[:, :, :n_frame]

        y_spec, v_spec = postprocess(mask, X_mag, X_phase)
        
        return y_spec, v_spec

    def spec_to_wav(self, spec):
        
        if self.high_end_process.startswith('mirroring'):        
            input_high_end_ = spec_utils.mirroring(self.high_end_process, spec, self.input_high_end, self.mp)
            wav = spec_utils.cmb_spectrogram_to_wave(spec, self.mp, self.input_high_end_h, input_high_end_)       
        else:
            wav = spec_utils.cmb_spectrogram_to_wave(spec, self.mp)
            
        return wav
   
def process_secondary_model(secondary_model: ModelData, process_data, main_model_primary_stem_4_stem=None, is_4_stem_demucs=False, main_process_method=None, is_pre_proc_model=False):
        
    if not is_pre_proc_model:
        process_iteration = process_data['process_iteration']
        process_iteration()
    
    if secondary_model.process_method == VR_ARCH_TYPE:
        seperator = SeperateVR(secondary_model, process_data, main_model_primary_stem_4_stem=main_model_primary_stem_4_stem, main_process_method=main_process_method)
    if secondary_model.process_method == MDX_ARCH_TYPE:
        if secondary_model.is_mdx_c:
            seperator = SeperateMDXC(secondary_model, process_data, main_model_primary_stem_4_stem=main_model_primary_stem_4_stem, main_process_method=main_process_method)
        else:
            seperator = SeperateMDX(secondary_model, process_data, main_model_primary_stem_4_stem=main_model_primary_stem_4_stem, main_process_method=main_process_method)
    if secondary_model.process_method == DEMUCS_ARCH_TYPE:
        seperator = SeperateDemucs(secondary_model, process_data, main_model_primary_stem_4_stem=main_model_primary_stem_4_stem, main_process_method=main_process_method)
        
    secondary_sources = seperator.seperate()

    if type(secondary_sources) is dict and not is_4_stem_demucs and not is_pre_proc_model:
        return gather_sources(secondary_model.primary_model_primary_stem, STEM_PAIR_MAPPER[secondary_model.primary_model_primary_stem], secondary_sources)
    else:
        return secondary_sources
    
def gather_sources(primary_stem_name, secondary_stem_name, secondary_sources: dict):
    
    source_primary = False
    source_secondary = False

    for key, value in secondary_sources.items():
        if key in primary_stem_name:
            source_primary = value
        if key in secondary_stem_name:
            source_secondary = value

    return source_primary, source_secondary
        
def prepare_mix(mix):
    
    audio_path = mix

    if not isinstance(mix, np.ndarray):
        mix, sr = librosa.load(mix, mono=False, sr=44100)
  
    else:
        mix = mix.T

    if not np.any(mix) and audio_path.endswith('.mp3'):
        mix = rerun_mp3(audio_path)

    if mix.ndim == 1:
        mix = np.asfortranarray([mix,mix])

    return mix

def rerun_mp3(audio_file, sample_rate=44100):

    with audioread.audio_open(audio_file) as f:
        track_length = int(f.duration)

    return librosa.load(audio_file, duration=track_length, mono=False, sr=sample_rate)[0]

def save_format(audio_path, save_format, mp3_bit_set):
    
    if not save_format == WAV:
        
        if OPERATING_SYSTEM == 'Darwin':
            FFMPEG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg')
            pydub.AudioSegment.converter = FFMPEG_PATH
        
        musfile = pydub.AudioSegment.from_wav(audio_path)
        
        if save_format == FLAC:
            audio_path_flac = audio_path.replace(".wav", ".flac")
            musfile.export(audio_path_flac, format="flac")  
        
        if save_format == MP3:
            audio_path_mp3 = audio_path.replace(".wav", ".mp3")
            musfile.export(audio_path_mp3, format="mp3", bitrate=mp3_bit_set)
        
        try:
            os.remove(audio_path)
        except Exception as e:
            print(e)
            
def pitch_shift(mix):
    new_sr = 31183

    # Resample audio file
    resampled_audio = signal.resample_poly(mix, new_sr, 44100)
    
    return resampled_audio

def list_to_dictionary(lst):
    dictionary = {item: index for index, item in enumerate(lst)}
    return dictionary

def vr_denoiser(X, device, hop_length=1024, n_fft=2048, cropsize=256, is_deverber=False):
    batchsize = 4

    denoiser_loc = os.path.join("lib_v5", "denoiser_lite.pth")
    deverber = os.path.join("lib_v5", "deverber.pth")
    
    utl_model = deverber if is_deverber else denoiser_loc
    
    if is_deverber:
        nout, nout_lstm = 64, 128
        mp = ModelParameters(os.path.join('lib_v5', 'vr_network', 'modelparams', '4band_v3.json'))
        n_fft = mp.param['bins'] * 2
    else:
        mp = None
        hop_length=1024
        nout, nout_lstm = 16, 128
    
    model = nets_new.CascadedNet(n_fft, nout=nout, nout_lstm=nout_lstm)
    model.load_state_dict(torch.load(utl_model, map_location=device))
    model.to(device)

    if mp is None:
        X_spec = spec_utils.wave_to_spectrogram(X, hop_length, n_fft)
    else:
        X_spec = loading_mix(X.T, mp)
   
    #PreProcess
    X_mag = np.abs(X_spec)
    X_phase = np.angle(X_spec)

    #Sep
    n_frame = X_mag.shape[2]
    pad_l, pad_r, roi_size = spec_utils.make_padding(n_frame, cropsize, model.offset)
    X_mag_pad = np.pad(X_mag, ((0, 0), (0, 0), (pad_l, pad_r)), mode='constant')
    X_mag_pad /= X_mag_pad.max()

    X_dataset = []
    patches = (X_mag_pad.shape[2] - 2 * model.offset) // roi_size
    for i in range(patches):
        start = i * roi_size
        X_mag_crop = X_mag_pad[:, :, start:start + cropsize]
        X_dataset.append(X_mag_crop)

    X_dataset = np.asarray(X_dataset)

    model.eval()
    
    with torch.no_grad():
        mask = []
        # To reduce the overhead, dataloader is not used.
        for i in tqdm(range(0, patches, batchsize)):
            X_batch = X_dataset[i: i + batchsize]
            X_batch = torch.from_numpy(X_batch).to(device)

            pred = model.predict_mask(X_batch)

            pred = pred.detach().cpu().numpy()
            pred = np.concatenate(pred, axis=2)
            mask.append(pred)

        mask = np.concatenate(mask, axis=2)
    
    mask = mask[:, :, :n_frame]

    #Post Proc
    if is_deverber:
        v_spec = mask * X_mag * np.exp(1.j * X_phase)
    else:
        v_spec = (1 - mask) * X_mag * np.exp(1.j * X_phase)

    if mp is None:
        wave = spec_utils.spectrogram_to_wave_old(v_spec, hop_length=1024)
        wave = spec_utils.match_array_shapes(wave, X)
    else:
        wave = spec_utils.cmb_spectrogram_to_wave(v_spec, mp).T

    return wave


def loading_mix(X, mp):

    X_wave, X_spec_s = {}, {}
    
    bands_n = len(mp.param['band'])
    
    for d in range(bands_n, 0, -1):        
        bp = mp.param['band'][d]
    
        if OPERATING_SYSTEM == 'Darwin':
            wav_resolution = 'polyphase' if SYSTEM_PROC == ARM or ARM in SYSTEM_ARCH else bp['res_type']
        else:
            wav_resolution = 'polyphase'#bp['res_type']
    
        if d == bands_n: # high-end band
            X_wave[d] = X

        else: # lower bands
            X_wave[d] = librosa.resample(X_wave[d+1], mp.param['band'][d+1]['sr'], bp['sr'], res_type=wav_resolution)
            
        X_spec_s[d] = spec_utils.wave_to_spectrogram_mt(X_wave[d], bp['hl'], bp['n_fft'], mp.param['mid_side'], 
                                                        mp.param['mid_side_b2'], mp.param['reverse'])
        
        # if d == bands_n and is_high_end_process:
        #     input_high_end_h = (bp['n_fft']//2 - bp['crop_stop']) + (mp.param['pre_filter_stop'] - mp.param['pre_filter_start'])
        #     input_high_end = X_spec_s[d][:, bp['n_fft']//2-input_high_end_h:bp['n_fft']//2, :]

    X_spec = spec_utils.combine_spectrograms(X_spec_s, mp)
    
    del X_wave, X_spec_s

    return X_spec

# def spec_to_wav(spec, is_high_end_process=False):
    
#     if is_high_end_process:        
#         input_high_end_ = spec_utils.mirroring('mirroring', spec, input_high_end, mp)
#         wav = spec_utils.cmb_spectrogram_to_wave(spec, mp, input_high_end_h, input_high_end_)       
#     else:
#         wav = spec_utils.cmb_spectrogram_to_wave(spec, mp)
        
#     return wav