from .base import MetaWorkflow, load_config, register_workflow
from traits.api import HasTraits, Directory, Bool, Button
import traits.api as traits
import os
import nipype.interfaces.freesurfer as fs
import nipype.interfaces.fsl as fsl
import nipype.pipeline.engine as pe
import nipype.interfaces.utility as niu
import nipype.interfaces.io as nio

"""
MetaWorkflow
"""
desc = """
Localizer Workflow
==================

"""
mwf = MetaWorkflow()
mwf.uuid = 'localizer'
mwf.tags = ['localizer','surface']
mwf.help = desc

"""
Config
"""

class config(HasTraits):
    uuid = traits.Str(desc="UUID")

    # Directories
    working_dir = Directory(mandatory=True, desc="Location of the Nipype working directory")
    base_dir = Directory(os.path.abspath('.'),mandatory=True, desc='Base directory of data. (Should be subject-independent)')
    sink_dir = Directory(mandatory=True, desc="Location where the BIP will store the results")
    crash_dir = Directory(mandatory=False, desc="Location to store crash files")
    surf_dir = Directory(desc="freesurfer directory. subject id's should be the same")

    # Execution
    run_using_plugin = Bool(False, usedefault=True, desc="True to run pipeline with plugin, False to run serially")
    plugin = traits.Enum("PBS", "MultiProc", "SGE", "Condor",
        usedefault=True,
        desc="plugin to use, if run_using_plugin=True")
    plugin_args = traits.Dict({"qsub_args": "-q many"},
        usedefault=True, desc='Plugin arguments.')
    test_mode = Bool(False, mandatory=False, usedefault=True,
        desc='Affects whether where and if the workflow keeps its \
                            intermediary files. True to keep intermediary files. ')
    # Data
    subject_id = traits.String()
    contrast = traits.File()
    mask_contrast = traits.File()
    use_contrast_mask = traits.Bool(True)
    reg_file = traits.File()
    mean_image = traits.File()
    roi = traits.Enum('superiortemporal',
                       'bankssts',
                       'caudalanteriorcingulate',
                       'caudalmiddlefrontal',
                       'corpuscallosum',
                       'cuneus',
                       'entorhinal',
                       'fusiform',
                       'inferiorparietal',
                       'inferiortemporal',
                       'isthmuscingulate',
                       'lateraloccipital',
                       'lateralorbitofrontal',
                       'lingual',
                       'medialorbitofrontal',
                       'middletemporal',
                       'parahippocampal',
                       'paracentral',
                       'parsopercularis',
                       'parsorbitalis',
                       'parstriangularis',
                       'pericalcarine',
                       'postcentral',
                       'posteriorcingulate',
                       'precentral',
                       'precuneus',
                       'rostralanteriorcingulate',
                       'rostralmiddlefrontal',
                       'superiorfrontal',
                       'superiorparietal',
                       'supramarginal',
                       'frontalpole',
                       'temporalpole',
                       'transversetemporal',
                       'insula') #35 freesurfer regions,
    thresh = traits.Float(1.5)


def create_config():
    c = config()
    c.uuid = mwf.uuid

    return c

mwf.config_ui = create_config

"""
View
"""

def create_view():
    from traitsui.api import View, Item, Group
    from traitsui.menu import OKButton, CancelButton
    view = View(Group(Item(name='working_dir'),
        Item(name='sink_dir'),
        Item(name='crash_dir'), Item(name='surf_dir'),
        label='Directories', show_border=True),
        Group(Item(name='run_using_plugin'),
            Item(name='plugin', enabled_when="run_using_plugin"),
            Item(name='plugin_args', enabled_when="run_using_plugin"),
            Item(name='test_mode'),
            label='Execution Options', show_border=True),
        Group(Item('subject_id'),
            Item(name='contrast'),
            Item(name='mask_contrast'),
            Item(name='use_contrast_mask'),
            Item(name='reg_file'), Item(name='mean_image'), Item(name='roi'), Item(name='thresh'),
            label='Data', show_border=True),
        buttons=[OKButton, CancelButton],
        resizable=True,
        width=1050)
    return view

mwf.config_view = create_view

"""
Construct Workflow
"""

def get_surface_label(vertex, hemi,subject, overlay, reg, sd, thresh = 2.0):
    import os
    if not os.environ["SUBJECTS_DIR"] == sd:
        os.environ["SUBJECTS_DIR"] = sd
    tcl_filename = os.path.abspath('hemi_%s_vertex_%d_subject_%s.tcl'%(hemi,vertex,subject))
    filename = os.path.abspath('%s_label.label'%hemi)
    tcl = """select_vertex_by_vno %d
mark_vertex %d on
redraw
puts "selected vertex"
fill_flood_from_cursor 0 0 0 0 1 0 1 argument
redraw
labl_save label1 %s
exit"""%(vertex, vertex, filename)
    a = open(tcl_filename,'w')
    a.write(tcl)
    a.close()
    cmd = 'tksurfer %s %s inflated -overlay %s -reg %s -abs -fthresh %s -tcl %s'%(subject, hemi, overlay, reg, thresh, tcl_filename)
    os.system(cmd)
    return filename

def get_vertices(sub,sd,overlay,reg,mean,hemi,roi='superiortemporal',thresh=1.5):
    import os
    import nibabel as nib
    import numpy as np
    outfile = os.path.abspath('%s.mgz'%hemi)
    cmd = 'mri_vol2surf --mov %s --ref %s --reg %s --o %s --sd %s --hemi %s'%(overlay,mean,reg,outfile,sd, hemi)
    os.system(cmd)
    img = nib.load(outfile)
    data = np.squeeze(img.get_data())
    datax = (np.abs(data) > thresh).astype(int)
    values = nib.freesurfer.read_annot('%s/label/%s.aparc.annot'%(os.path.join(sd,sub),hemi))
    names = values[2]
    names_idx = np.asarray(range(len(names)))[np.asarray(names)==roi]
    names_idx = names_idx[0]
    idxs = np.asarray(range(0,img.shape[0]))
    foo = (np.asarray(values[0]) == names_idx).astype(int)
    valid_idxs = idxs[(datax + foo) ==2]
    goo = data[(foo + datax)==2]
    return int(valid_idxs[np.argmax(goo)])


def localizer(name='localizer'):
    wf = pe.Workflow(name=name)
    inputspec = pe.Node(niu.IdentityInterface(fields=["subject_id",
                                                      "subjects_dir",
                                                      "overlay",
                                                      'reg',
                                                      'mean','thresh','roi']),name='inputspec')
    surf_label = pe.MapNode(niu.Function(input_names=['vertex',
                                                   'hemi',
                                                   'subject',
                                                   'overlay',
                                                   'reg',
                                                   'sd',
                                                   'thresh'],
                                      output_names=['filename'],
                                      function=get_surface_label),
        name='get_surface_label', iterfield=['hemi','vertex'])
    surf_label.inputs.hemi=['lh','rh']
    #surf_label.inputs.vertex = [61091, 60437]
    #surf_label.inputs.thresh = 1.5
    wf.connect(inputspec,"subject_id",surf_label,"subject")
    wf.connect(inputspec,"subjects_dir",surf_label,"sd")
    wf.connect(inputspec,"overlay",surf_label,"overlay")
    wf.connect(inputspec,"reg",surf_label,"reg")

    label2vol = pe.Node(fs.Label2Vol(),name='labels2vol')
    wf.connect(inputspec,'subjects_dir',label2vol,'subjects_dir')
    wf.connect(inputspec,'mean',label2vol,'template_file')
    wf.connect(inputspec,'reg',label2vol,'reg_file')
    wf.connect(surf_label,'filename',label2vol,'label_file')

    verts = pe.MapNode(niu.Function(input_names=['sub',
                                              'sd',
                                              'overlay',
                                              'reg',
                                              'mean',
                                              'hemi',
                                              'roi',
                                              'thresh'],
                                 output_names=['vertex'],
                                 function=get_vertices),
        name='get_verts',iterfield=['hemi'])
    verts.inputs.hemi = ['lh','rh']
    wf.connect(inputspec,'subject_id',verts,'sub')
    wf.connect(inputspec,'subjects_dir',verts,'sd')
    wf.connect(inputspec,'overlay',verts,'overlay')
    wf.connect(inputspec,'reg',verts,'reg')
    wf.connect(inputspec,'mean',verts,'mean')
    wf.connect(inputspec,'thresh',verts,'thresh')
    wf.connect(inputspec,'roi',verts,'roi')
    wf.connect(verts,'vertex',surf_label,'vertex')
    wf.connect(inputspec,'thresh',surf_label,'thresh')

    outputspec = pe.Node(niu.IdentityInterface(fields=['rois']),name='outputspec')

    bin = pe.Node(fsl.ImageMaths(op_string = '-bin'),name="binarize_roi")
    changetype = pe.Node(fsl.ChangeDataType(output_datatype='short'),name='to_short')


    wf.connect(label2vol,'vol_label_file',bin,'in_file')
    wf.connect(bin,'out_file', changetype, 'in_file')
    wf.connect(changetype, 'out_file', outputspec, 'rois')
    return wf

mwf.workflow_function = localizer

"""
Main
"""
def main(config_file):
    c = load_config(config_file,config)
    wk = localizer()
    if c.test_mode:
        wk.write_graph()

    sinker = pe.Node(nio.DataSink(),name='sinker')
    outputspec = wk.get_node('outputspec')
    wk.connect(outputspec,'rois', sinker,'mask')
    sinker.inputs.container = c.subject_id
    sinker.inputs.substitutions = [('_labels2vol0',''),
                                   ('_labels2vol1',''),
                                   ('lh_label_vol_maths_chdt.nii','roi.nii')]


    sinker.inputs.base_directory = c.sink_dir
    wk.inputs.inputspec.subject_id = c.subject_id
    wk.inputs.inputspec.subjects_dir = c.surf_dir
    wk.inputs.inputspec.overlay = c.contrast
    wk.inputs.inputspec.mean = c.mean_image
    wk.inputs.inputspec.reg = c.reg_file
    wk.inputs.inputspec.thresh = c.thresh
    wk.inputs.inputspec.roi = c.roi
    wk.base_dir = c.working_dir
    if c.run_using_plugin:
        wk.run(plugin=c.plugin,plugin_args=c.plugin_args)
    else:
        wk.run()

mwf.workflow_main_function = main
"""
Register Workflow
"""
register_workflow(mwf)
