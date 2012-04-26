import os
import nipype.pipeline.engine as pe
import nipype.interfaces.utility as util
import nipype.interfaces.io as nio
from bips.utils.reportsink.io import ReportSink
from .base import MetaWorkflow, load_config, register_workflow
from scripts.u0a14c5b5899911e1bca80023dfa375f2.QA_utils import corr_image, vol2surf

desc = """
Resting State correlation QA workflow
=====================================

"""
mwf = MetaWorkflow()
mwf.uuid = '62aff7328b0a11e1be5d001e4fb1404c'
mwf.tags = ['resting','fMRI','QA','correlation']
mwf.uses_outputs_of = ['7757e3168af611e1b9d5001e4fb1404c']
mwf.help = desc
# Define Workflow

addtitle = lambda x: "Resting_State_Correlations_fwhm%s"%str(x)


def start_config_table(c):
    import numpy as np
    param_names = np.asarray(['motion', 'composite norm', 'compcorr components', 'outliers', 'motion derivatives'])
    boolparams=np.asarray(c.reg_params)
    params = param_names[boolparams]
    table = []
    table.append(['TR',str(c.TR)])
    table.append(['Slice Order',str(c.SliceOrder)])
    if c.use_fieldmap:
        table.append(['Echo Spacing',str(c.echospacing)])
        table.append(['Fieldmap Smoothing',str(c.sigma)])
        table.append(['TE difference',str(c.TE_diff)])
    table.append(['Art: norm thresh',str(c.norm_thresh)])
    table.append(['Art: z thresh',str(c.z_thresh)])
    table.append(['fwhm',str(c.fwhm)])
    table.append(['highpass freq',str(c.highpass_freq)])
    table.append(['lowpass freq',str(c.lowpass_freq)])
    table.append(['Regressors',str(params)])
    return [[table]]



def resting_datagrab(c,name="resting_datagrabber"):
    datasource = pe.Node(interface=nio.DataGrabber(infields=['subject_id',
                                                             'fwhm'],
                                                   outfields=['reg_file',
                                                              'mean_image',
                                                              "mask",
                                                              "func"]),
                         name = name)
    datasource.inputs.base_directory = os.path.join(c.sink_dir)
    datasource.inputs.template ='*'
    datasource.inputs.field_template = dict(reg_file='%s/preproc/bbreg/*.dat',
                                            mean_image='%s/preproc/mean/*.nii.gz',
                                            mask='%s/preproc/mask/*_brainmask.nii',
                                            func="%s/preproc/output/fwhm_%s/%s_r??_bandpassed.nii.gz")
    datasource.inputs.template_args = dict(reg_file=[['subject_id']],
                                           mean_image=[['subject_id']],
                                           mask=[['subject_id']],
                                           func=[['subject_id','fwhm','subject_id']])
    return datasource

def resting_QA(c,QA_c, name="resting_QA"):
    
    workflow=pe.Workflow(name=name)
    inputspec = pe.Node(interface=util.IdentityInterface(fields=["in_files",
                                                                 "reg_file",
                                                                 "subjects_dir",
                                                                 "mean_image"]), name="inputspec")
    infosource = pe.Node(util.IdentityInterface(fields=['subject_id']),
                         name='subject_names')
    if QA_c.test_mode:
        infosource.iterables = ('subject_id', [c.subjects[0]])
    else:
        infosource.iterables = ('subject_id', c.subjects)
    
    fwhmsource = pe.Node(util.IdentityInterface(fields=['fwhm']),
                         name='fwhm_source')
    fwhmsource.iterables = ('fwhm',c.fwhm)
    dataflow = resting_datagrab(c)
    workflow.connect(fwhmsource,'fwhm',dataflow,'fwhm')
    workflow.connect(infosource,'subject_id',dataflow,'subject_id')
    workflow.connect(dataflow,'func', inputspec,'in_files')
    workflow.connect(dataflow,'reg_file', inputspec, 'reg_file')
    workflow.inputs.inputspec.subjects_dir = c.surf_dir
    workflow.connect(dataflow,'mean_image', inputspec,'mean_image')
    
    tosurf = pe.MapNode(util.Function(input_names=['input_volume',
                                                'ref_volume',
                                                'reg_file',
                                                'trg',
                                                'hemi'],
                                   output_names=["out_file"],
                                   function=vol2surf), name='vol2surf',iterfield=["input_volume"])
    tosurf.inputs.hemi = 'lh'
    tosurf.inputs.trg = 'fsaverage5'
    
    workflow.connect(inputspec,'in_files',tosurf,'input_volume')
    workflow.connect(inputspec,'reg_file',tosurf,'reg_file')
    workflow.connect(inputspec,'mean_image', tosurf,'ref_volume')
    
    to_img = pe.MapNode(util.Function(input_names=['resting_image','fwhm'],
                                   output_names=["corr_image",
                                                 "ims",
                                                 "roitable",
                                                 "histogram",
                                                 "corrmat_npz"],
                                   function=corr_image),
                        name="image_gen",iterfield=["resting_image"])
                     
    workflow.connect(tosurf,'out_file',to_img,'resting_image')
    workflow.connect(fwhmsource,'fwhm',to_img,'fwhm')
    
    sink = pe.Node(ReportSink(orderfields=["Introduction",
                                           "Subject",
                                           "Configuration",
                                           "Correlation_Images",
                                           "Other_Views",
                                           "ROI_Table",
                                           "Histogram"]),
                   name="write_report")
    sink.inputs.base_directory = os.path.join(QA_c.sink_dir)
    sink.inputs.json_sink = QA_c.json_sink
    sink.inputs.Introduction = "Resting state correlations with seed at precuneus"
    sink.inputs.Configuration = start_config_table(c)
    
    corrmat_sinker = pe.Node(nio.DataSink(),name='corrmat_sink')
    corrmat_sinker.inputs.base_directory = QA_c.json_sink
    
    def get_substitutions(subject_id):
        subs = [('_fwhm_','fwhm'),('_subject_id_%s'%subject_id,'')]
        for i in range(20):
            subs.append(('_image_gen%d/corrmat.npz'%i,'corrmat%02d.npz'%i))
        return subs

    workflow.connect(infosource,('subject_id',get_substitutions),corrmat_sinker,'substitutions')
    workflow.connect(infosource,'subject_id',corrmat_sinker,'container')
    workflow.connect(to_img,'corrmat_npz',corrmat_sinker,'corrmats')
    
    #sink.inputs.report_name = "Resting_State_Correlations"
    workflow.connect(infosource,'subject_id',sink,'Subject')
    workflow.connect(fwhmsource,('fwhm',addtitle),sink,'report_name')
    workflow.connect(infosource,'subject_id',sink,'container')
    workflow.connect(to_img,"corr_image",sink,"Correlation_Images")
    workflow.connect(to_img,"ims",sink,"Other_Views")
    workflow.connect(to_img,"roitable",sink,"ROI_Table")
    workflow.connect(to_img,"histogram",sink,"Histogram")
    
    return workflow

from .workflow3 import config

def create_config():
    c = config()
    c.uuid = mwf.uuid
    c.desc = mwf.help
    return c

from .workflow2 import create_config as prep_config

def create_view():
    from traitsui.api import View, Item, Group, CSVListEditor
    from traitsui.menu import OKButton, CancelButton
    view = View(Group(Item(name='uuid', style='readonly'),
        Item(name='desc', style='readonly'),
        label='Description', show_border=True),
        Group(Item(name='working_dir'),
            Item(name='sink_dir'),
            Item(name='crash_dir'),
            Item(name='json_sink'),
            label='Directories', show_border=True),
        Group(Item(name='run_using_plugin'),
            Item(name='plugin', enabled_when="run_using_plugin"),
            Item(name='plugin_args', enabled_when="run_using_plugin"),
            Item(name='test_mode'),
            label='Execution Options', show_border=True),
        Group(Item(name='subjects', editor=CSVListEditor()),
            label='Subjects', show_border=True),
        Group(Item(name='preproc_config'),
            label = 'Preprocessing Info'),
        buttons = [OKButton, CancelButton],
        resizable=True,
        width=1050)
    return view

# Define Main
def main(config):
    
    QA_config = load_config(config,create_config)
    c = load_config(QA_config.preproc_config, prep_config)

    a = resting_QA(c,QA_config)
    a.base_dir = QA_config.working_dir
    if QA_config.test_mode:
        a.write_graph()
    a.config = {'execution' : {'crashdump_dir' : QA_config.crash_dir}}
    if not os.environ['SUBJECTS_DIR'] == c.surf_dir:
        print "Your SUBJECTS_DIR is incorrect!"
        print "export SUBJECTS_DIR=%s"%c.surf_dir
    else:
        if QA_config.run_using_plugin:
            a.run(plugin=QA_config.plugin,plugin_args=QA_config.plugin_args)
        else:
            a.run()


mwf.config_ui = create_config
mwf.config_view = create_view
mwf.workflow_main_function = main
register_workflow(mwf)

