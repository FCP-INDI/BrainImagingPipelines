import os

from traits.api import HasTraits, Directory, Bool, Button
import traits.api as traits


import nipype.pipeline.engine as pe
import nipype.interfaces.utility as util
import nipype.interfaces.io as nio

from .base import MetaWorkflow, load_config, register_workflow

mwf = MetaWorkflow()
mwf.help = """
Task preprocessing workflow
===========================

"""
mwf.uuid = '63fcbb0a890211e183d30023dfa375f2'
mwf.tags = ['task','fMRI','preprocessing','fsl','freesurfer','nipy']
mwf.script_dir = 'u0a14c5b5899911e1bca80023dfa375f2'

# create gui
class config(HasTraits):
    uuid = traits.Str(desc="UUID")
    desc = traits.Str(desc='Workflow description')
    # Directories
    working_dir = Directory(mandatory=True, desc="Location of the Nipype working directory")
    base_dir = Directory(mandatory=True, desc='Base directory of data. (Should be subject-independent)')
    sink_dir = Directory(mandatory=True, desc="Location where the BIP will store the results")
    field_dir = Directory(desc="Base directory of field-map data (Should be subject-independent) \
                                                 Set this value to None if you don't want fieldmap distortion correction")
    crash_dir = Directory(mandatory=False, desc="Location to store crash files")
    json_sink = Directory(mandatory=False, desc= "Location to store json_files")
    surf_dir = Directory(mandatory=True, desc= "Freesurfer subjects directory")
    
    # Execution
    
    run_using_plugin = Bool(False, usedefault=True, desc="True to run pipeline with plugin, False to run serially")
    plugin = traits.Enum("PBS", "PBSGraph","MultiProc", "SGE", "Condor",
                         usedefault=True,
                         desc="plugin to use, if run_using_plugin=True")
    plugin_args = traits.Dict({"qsub_args": "-q many"},
                              usedefault=True, desc='Plugin arguments.')
    test_mode = Bool(False, mandatory=False, usedefault=True,
                            desc='Affects whether where and if the workflow keeps its \
                            intermediary files. True to keep intermediary files. ')
    # Subjects
    
    subjects= traits.List(traits.Str, mandatory=True, usedefault=True,
                          desc="Subject id's. Note: These MUST match the subject id's in the \
                                Freesurfer directory. For simplicity, the subject id's should \
                                also match with the location of individual functional files.")
    func_template = traits.String('%s/functional.nii.gz')
    run_datagrabber_without_submitting = traits.Bool(desc="Run the datagrabber without \
    submitting to the cluster")

    # Fieldmap
    
    use_fieldmap = Bool(False, mandatory=False, usedefault=True,
                               desc='True to include fieldmap distortion correction. Note: field_dir \
                                     must be specified')
    magnitude_template = traits.String('%s/magnitude.nii.gz')
    phase_template = traits.String('%s/phase.nii.gz')
    TE_diff = traits.Float(desc='difference in B0 field map TEs')
    sigma = traits.Int(2, desc='2D spatial gaussing smoothing stdev (default = 2mm)')
    echospacing = traits.Float(desc="EPI echo spacing")
    
    # Motion Correction

    do_slicetiming = Bool(True, usedefault=True, desc="Perform slice timing correction")
    SliceOrder = traits.List(traits.Int)
    TR = traits.Float(mandatory=True, desc = "TR of functional")
    motion_correct_node = traits.Enum('nipy','fsl','spm',
                                      desc="motion correction algorithm to use",
                                      usedefault=True,)
    
    # Artifact Detection
    
    norm_thresh = traits.Float(1, min=0, usedefault=True, desc="norm thresh for art")
    z_thresh = traits.Float(3, min=0, usedefault=True, desc="z thresh for art")
    
    # Smoothing
    fwhm = traits.List([0, 5], traits.Float(), mandatory=True, usedefault=True,
                       desc="Full width at half max. The data will be smoothed at all values \
                             specified in this list.")
                             
    # CompCor
    compcor_select = traits.BaseTuple(traits.Bool, traits.Bool, mandatory=True,
                                  desc="The first value in the list corresponds to applying \
                                       t-compcor, and the second value to a-compcor. Note: \
                                       both can be true")
    num_noise_components = traits.Int(6, usedefault=True, 
                                      desc="number of principle components of the noise to use")
    # Highpass Filter
    hpcutoff = traits.Float(128., desc="highpass cutoff", usedefault=True)

    # Advanced Options
    use_advanced_options = traits.Bool()
    advanced_script = traits.Code()

    # Buttons
    check_func_datagrabber = Button("Check")
    check_field_datagrabber = Button("Check")

    def _check_func_datagrabber_fired(self):
        subs = self.subjects
        
        for s in subs:
            if not os.path.exists(os.path.join(self.base_dir,self.func_template % s)):
                print "ERROR", os.path.join(self.base_dir,self.func_template % s), "does NOT exist!"
                break
            else:
                print os.path.join(self.base_dir,self.func_template % s), "exists!"

    def _check_field_datagrabber_fired(self):
        subs = self.subjects
        
        for s in subs:
            if not os.path.exists(os.path.join(self.field_dir,self.magnitude_template % s)):
                print "ERROR:", os.path.join(self.field_dir,self.magnitude_template % s), "does NOT exist!"
                break
            else:
                print os.path.join(self.base_dir,self.magnitude_template % s), "exists!"
            if not os.path.exists(os.path.join(self.field_dir,self.phase_template % s)):
                print "ERROR:", os.path.join(self.field_dir,self.phase_template % s), "does NOT exist!"
                break
            else:
                print os.path.join(self.base_dir,self.phase_template % s), "exists!"

def create_config():
    c = config()
    c.uuid = mwf.uuid
    c.desc = mwf.help
    return c

# create workflow

from scripts.u0a14c5b5899911e1bca80023dfa375f2.base import (create_prep,
                                                            create_prep_fieldmap)
from scripts.u0a14c5b5899911e1bca80023dfa375f2.utils import (get_datasink,
                                                             get_substitutions)

def get_dataflow(c):
    dataflow = pe.Node(interface=nio.DataGrabber(infields=['subject_id'],
                                                   outfields=['func']),
                         name = "preproc_dataflow",
                         run_without_submitting=c.run_datagrabber_without_submitting)
    dataflow.inputs.base_directory = c.base_dir
    dataflow.inputs.template ='*'
    dataflow.inputs.sort_filelist = True
    dataflow.inputs.field_template = dict(func=c.func_template)
    dataflow.inputs.template_args = dict(func=[['subject_id']])
    return dataflow
    
def prep_workflow(c, fieldmap):
    
    infosource = pe.Node(util.IdentityInterface(fields=['subject_id']),
                         name='subject_names')
    if not c.test_mode:
        infosource.iterables = ('subject_id', c.subjects)
    else:
        infosource.iterables = ('subject_id', c.subjects[:1])

    modelflow = pe.Workflow(name='preproc')
    
    # make a data sink
    sinkd = get_datasink(c.sink_dir, c.fwhm)
    
    # generate preprocessing workflow
    #dataflow = c.create_dataflow()
    
    import nipype.interfaces.io as nio 
    # create a node to obtain the functional images
    dataflow = get_dataflow(c)

    if fieldmap:
        preproc = create_prep_fieldmap()
        preproc.inputs.inputspec.FM_Echo_spacing = c.echospacing
        preproc.inputs.inputspec.FM_TEdiff = c.TE_diff
        preproc.inputs.inputspec.FM_sigma = c.sigma
        
        #datasource_fieldmap = c.create_fieldmap_dataflow()
        datasource_fieldmap = pe.Node(nio.DataGrabber(infields=['subject_id'],
                                                      outfields=['mag',
                                                                 'phase']),
                                      name = "fieldmap_datagrabber")
        datasource_fieldmap.inputs.base_directory = c.field_dir
        datasource_fieldmap.inputs.sort_filelist = True
        datasource_fieldmap.inputs.template ='*'
        datasource_fieldmap.inputs.field_template = dict(mag=c.magnitude_template,
                                                         phase=c.phase_template)
        datasource_fieldmap.inputs.template_args = dict(mag=[['subject_id']],
                                                        phase=[['subject_id']])
        
        
        modelflow.connect(infosource, 'subject_id',
                          datasource_fieldmap, 'subject_id')
        modelflow.connect(datasource_fieldmap,'mag',
                          preproc,'fieldmap_input.magnitude_file')
        modelflow.connect(datasource_fieldmap,'phase',
                          preproc,'fieldmap_input.phase_file')
        modelflow.connect(preproc, 'outputspec.FM_unwarped_mean',
                          sinkd, 'preproc.fieldmap.@unwarped_mean')
        modelflow.connect(preproc, 'outputspec.FM_unwarped_epi',
                          sinkd, 'preproc.fieldmap.@unwarped_epi')
    else:
        preproc = create_prep()

    preproc.inputs.inputspec.motion_correct_node = c.motion_correct_node
    preproc.inputs.inputspec.fssubject_dir = c.surf_dir
    preproc.get_node('fwhm_input').iterables = ('fwhm', c.fwhm)
    preproc.inputs.inputspec.highpass = c.hpcutoff/(2*c.TR)
    preproc.inputs.inputspec.num_noise_components = c.num_noise_components
    preproc.crash_dir = c.crash_dir
    preproc.inputs.inputspec.ad_normthresh = c.norm_thresh
    preproc.inputs.inputspec.ad_zthresh = c.z_thresh
    preproc.inputs.inputspec.tr = c.TR
    if c.do_slicetiming:
        preproc.inputs.inputspec.sliceorder = c.SliceOrder
        preproc.inputs.inputspec.interleaved = False # NOTE: This should be removed later
    preproc.inputs.inputspec.compcor_select = c.compcor_select
    
    # make connections
    modelflow.connect(infosource, 'subject_id',
                      sinkd, 'container')
    modelflow.connect(infosource, ('subject_id', get_substitutions,
                                   c.use_fieldmap),
                      sinkd, 'substitutions')
    modelflow.connect(infosource, 'subject_id',
                      dataflow, 'subject_id')
    modelflow.connect(infosource, 'subject_id', 
                      preproc, 'inputspec.fssubject_id')
    modelflow.connect(dataflow,'func',
                      preproc, 'inputspec.func')
    modelflow.connect(preproc, 'outputspec.mean',
                      sinkd, 'preproc.motion.reference')
    modelflow.connect(preproc, 'outputspec.motion_parameters',
                      sinkd, 'preproc.motion')
    modelflow.connect(preproc, 'outputspec.realigned_files',
                      sinkd, 'preproc.motion.realigned')
    modelflow.connect(preproc, 'outputspec.mean',
                      sinkd, 'preproc.meanfunc')
    #modelflow.connect(preproc, 'plot_motion.out_file',
    #                  sinkd, 'preproc.motion.@plots')
    modelflow.connect(preproc, 'outputspec.mask',
                      sinkd, 'preproc.mask')
    modelflow.connect(preproc, 'outputspec.outlier_files',
                      sinkd, 'preproc.art')
    modelflow.connect(preproc, 'outputspec.intensity_files',
                      sinkd, 'preproc.art.@intensity')
    modelflow.connect(preproc, 'outputspec.combined_motion',
                      sinkd, 'preproc.art.@norm')
    modelflow.connect(preproc, 'outputspec.outlier_stat_files',
                      sinkd, 'preproc.art.@stats')
    modelflow.connect(preproc, 'outputspec.reg_file',
                      sinkd, 'preproc.bbreg')
    modelflow.connect(preproc, 'outputspec.reg_cost',
                      sinkd, 'preproc.bbreg.@reg_cost')
    modelflow.connect(preproc, 'outputspec.highpassed_files',
                      sinkd, 'preproc.highpass')
    modelflow.connect(preproc, 'outputspec.smoothed_files',
                      sinkd, 'preproc.smooth')
    modelflow.connect(preproc, 'outputspec.tsnr_file',
                      sinkd, 'preproc.tsnr')
    modelflow.connect(preproc, 'outputspec.tsnr_detrended',
                      sinkd, 'preproc.tsnr.@detrended')
    modelflow.connect(preproc, 'outputspec.stddev_file',
                      sinkd, 'preproc.tsnr.@stddev')
    modelflow.connect(preproc, 'outputspec.z_img', 
                      sinkd, 'preproc.z_image')
    modelflow.connect(preproc, 'outputspec.noise_components',
                      sinkd, 'preproc.noise_components')
    

    modelflow.base_dir = os.path.join(c.working_dir, 'work_dir')
    return modelflow

def main(configfile):
    c = load_config(configfile, create_config)
    preprocess = prep_workflow(c, c.use_fieldmap)
    realign = preprocess.get_node('preproc.mod_realign')
    realign.plugin_args = {'qsub_args': '-l nodes=1:ppn=3'}
    #realign.inputs.loops = 2
    realign.inputs.speedup = 5
    realign.inputs.time_interp = c.do_slicetiming
    cc = preprocess.get_node('preproc.CompCor')
    cc.plugin_args = {'qsub_args': '-l nodes=1:ppn=3'}
    preprocess.config = {'execution': {'crashdump_dir': c.crash_dir}}

    if c.use_advanced_options:
        exec c.advanced_script

    if c.run_using_plugin:
        preprocess.run(plugin=c.plugin, plugin_args = c.plugin_args)
    else:
        preprocess.run()

def create_view():
    from traitsui.api import View, Item, Group, CSVListEditor, TupleEditor
    from traitsui.menu import OKButton, CancelButton
    view = View(Group(Item(name='uuid', style='readonly'),
                      Item(name='desc', style='readonly'),
                      label='Description', show_border=True),
                Group(Item(name='working_dir'),
                      Item(name='sink_dir'),
                      Item(name='crash_dir'),
                      Item(name='json_sink'),
                      Item(name='surf_dir'),
                      label='Directories', show_border=True),
                Group(Item(name='run_using_plugin'),
                      Item(name='plugin', enabled_when="run_using_plugin"),
                      Item(name='plugin_args', enabled_when="run_using_plugin"),
                      Item(name='test_mode'),
                      label='Execution Options', show_border=True),
                Group(Item(name='subjects', editor=CSVListEditor()),
                      Item(name='base_dir', ),
                      Item(name='func_template'),
                      Item(name='check_func_datagrabber'),
                      Item(name='run_datagrabber_without_submitting'),
                      label='Subjects', show_border=True),
                Group(Item(name='use_fieldmap'),
                      Item(name='field_dir', enabled_when="use_fieldmap"),
                      Item(name='magnitude_template',
                           enabled_when="use_fieldmap"),
                      Item(name='phase_template', enabled_when="use_fieldmap"),
                      Item(name='check_field_datagrabber',
                           enabled_when="use_fieldmap"),
                      Item(name='echospacing',enabled_when="use_fieldmap"),
                      Item(name='TE_diff',enabled_when="use_fieldmap"),
                      Item(name='sigma',enabled_when="use_fieldmap"),
                      label='Fieldmap',show_border=True),
                Group(Item(name="motion_correct_node"),
                      Item(name='TR'),
                      Item(name='do_slicetiming'),
                      Item(name='SliceOrder', editor=CSVListEditor()),
                      label='Motion Correction', show_border=True),
                Group(Item(name='norm_thresh'),
                      Item(name='z_thresh'),
                      label='Artifact Detection',show_border=True),
                Group(Item(name='compcor_select'),
                      Item(name='num_noise_components'),
                      label='CompCor',show_border=True),
                Group(Item(name='fwhm', editor=CSVListEditor()),
                      label='Smoothing',show_border=True),
                Group(Item(name='hpcutoff'),
                      label='Highpass Filter',show_border=True),
                Group(Item(name='use_advanced_options'),
                    Item(name='advanced_script',enabled_when='use_advanced_options'),
                    label='Advanced',show_border=True),
                buttons = [OKButton, CancelButton],
                resizable=True,
                width=1050)
    return view

mwf.workflow_main_function = main
mwf.config_ui = create_config
mwf.config_view = create_view

register_workflow(mwf)
