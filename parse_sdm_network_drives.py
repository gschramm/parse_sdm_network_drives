import pathlib
import pydicom
import pandas as pd
import argparse
from glob import glob

def parse_exams(root_dir, 
                extra_tags = None,
                verbose    = False):

  dcm_tags = ['StudyID', 'PatientID', 'PatientName', 'AcquisitionDate', 'StudyDescription']

  if not extra_tags is None:
    dcm_tags += extra_tags

  p  = pathlib.Path(root_dir)
  
  # get all the exam dirs
  edirs = list(p.glob('PESI/p*/e*'))
  
  exam_df = pd.DataFrame()
  
  for exam_dir in edirs:
  
    sdirs = list(exam_dir.glob('s*'))
    if len(sdirs) > 0: 
      first_series_dir = sdirs[0]
  
      dcm_files = list(first_series_dir.glob('*'))
      if len(dcm_files) > 0:
        first_dcm_file = dcm_files[0]
  
        with pydicom.read_file(first_dcm_file) as dcm:
          edict = {}
          for tag in dcm_tags:
            if tag in dcm:
              edict[tag] = dcm[tag].value
            else:
              edict[tag] = None

          edict['p_dir'] = exam_dir.parts[-2]
          edict['e_dir'] = exam_dir.parts[-1]
          exam_df = exam_df.append(pd.DataFrame(edict, index = [0]), ignore_index = True)  
          if verbose:
            print(exam_dir)
  
  if 'StudyID' in exam_df: 
    exam_df.StudyID = exam_df.StudyID.astype(int)
    exam_df.sort_values('StudyID', ignore_index = True, inplace = True)

  if 'AcquisitionDate' in exam_df:
    exam_df.AcquisitionDate = pd.to_datetime(exam_df.AcquisitionDate)

  exam_df.attrs['root'] = root_dir

  return exam_df

#----------------------------------------------------------------------------------------------

def parse_exam(exam_dir,
               dcm_tags = ['SeriesNumber', 'Modality','SeriesDescription', 'AcquisitionTime'],
               verbose  = False):
  
  exam_p    = pathlib.Path(exam_dir)
  series_df = pd.DataFrame()
  
  sdirs = list(exam_p.glob('s*'))
  
  if len(sdirs) > 0: 
    for sdir in sdirs: 
      dcm_files = list(sdir.glob('*'))
      if len(dcm_files) > 0:
        first_dcm_file = dcm_files[0]
    
        with pydicom.read_file(first_dcm_file) as dcm:
          edict = {}
          for tag in dcm_tags:
            if tag in dcm:
              edict[tag] = dcm[tag].value
            else:
              edict[tag] = None
  
          edict['s_dir']     = sdir.parts[-1]
          edict['n_files'] = len(dcm_files) 
          series_df = series_df.append(pd.DataFrame(edict, index = [0]), ignore_index = True)  
          if verbose:
            print(sdir)

  series_df.attrs['exam_dir'] = exam_dir

  return series_df

#----------------------------------------------------------------------------------------------

def check_exam_LM_files(series_df, verbose = False):
  
  lm_df = []

  for ir, lm_data in series_df.loc[series_df.Modality == 'GEMS PET LST'].iterrows():
    s_dir = lm_data.s_dir
    lm_dcm_dir   = pathlib.Path(series_df.attrs['exam_dir']) / s_dir
    lm_dcm_files = list(lm_dcm_dir.glob('*'))
  
    if len(lm_dcm_files) > 0:
 
      for lm_dcm_file in lm_dcm_files:
        with pydicom.read_file(lm_dcm_file) as dcm:
          series_desc = dcm.SeriesDescription

          if [0x0009,0x10da] in dcm:
            # dicom header of the actual listmode file
            BLF_file = pathlib.Path(lm_dcm_file.parents[4]) / dcm[0x0009,0x10da].value[1:]
            MRAC_info, MRAC_complete = check_MRAC(lm_dcm_file, series_df)
            lm_df.append([s_dir, series_desc, lm_dcm_file.parts[-1],  BLF_file, 'BLF', 
                          BLF_file.exists(), MRAC_complete,','.join(map(str,MRAC_info.SeriesNumber.values))])
          else:
            # geocal, norm or WCC dicom header
            if [0x17,0x1005] in dcm:
              corr_sino_file = pathlib.Path(lm_dcm_file.parents[4]) / dcm[0x0017,0x1007].value[1:]
              calib_type = dcm[0x17,0x1005].value

              if calib_type == '3D Geometric Calibration':
                lm_df.append([s_dir, series_desc, lm_dcm_file.parts[-1], corr_sino_file, 
                              '3D Geometric Calibration', corr_sino_file.exists(), None, None])
              elif calib_type == 'PET 3D Normalization':
                lm_df.append([s_dir, series_desc, lm_dcm_file.parts[-1], corr_sino_file, 
                              'PET 3D Normalization', corr_sino_file.exists(), None, None])
            else:
              # WCC dicom file  
              lm_df.append([s_dir, series_desc, lm_dcm_file.parts[-1], None, '3D WCC', True, None, None])


 
  lm_df = pd.DataFrame(lm_df, columns = ['s_dir','SeriesDescription','dcm_file','data_file','type',
                                         'data_file_exists', 'MRAC_complete','MRAC_series_nums'])
  lm_df.attrs = series_df.attrs.copy()

  return lm_df

#----------------------------------------------------------------------------------------------

def check_MRAC(lm_dcm_file, series_df):
  with pydicom.read_file(lm_dcm_file) as dcm:
    MRAC_info  = [[x[0x0023,0x1062].value, x[0x0023,0x1061].value, x[0x0023,0x1062].value in series_df.SeriesNumber.values] for x in dcm[0x0023,0x1060]]
  
  MRAC_info     = pd.DataFrame(MRAC_info, columns = ['SeriesNumber','Description', 'exists'])
  MRAC_complete = MRAC_info.exists.all() 

  return MRAC_info, MRAC_complete


#----------------------------------------------------------------------------------------------
#----------------------------------------------------------------------------------------------
#----------------------------------------------------------------------------------------------



parser = argparse.ArgumentParser(description='Parse GE scan data manager network drive')

parser.add_argument('sdir', help='subdirectory to parse (e.g. petmr_2107)')
parser.add_argument('--mdir', default = '/uz/data/Admin/ngepetmr',  
                     help = 'master (root) directory - default (/uz/data/Admin/ngepetmr)')
args = parser.parse_args()

exam_data_frame = parse_exams(pathlib.Path(args.mdir) / args.sdir)

study_data_frames    = {}
listmode_data_frames = {}

writer = pd.ExcelWriter(f'{args.sdir}.xlsx', engine = 'xlsxwriter')
exam_data_frame.to_excel(writer, sheet_name = 'exams')

for i, ex in exam_data_frame.iterrows():
  print(ex) 
  print('')
  
  exam_path = pathlib.Path(exam_data_frame.attrs['root']) / 'PESI' / ex.p_dir / ex.e_dir
  sdf                           = parse_exam(exam_path) 
  study_data_frames[ex.StudyID] = sdf
  study_data_frames[ex.StudyID].attrs['exam_details'] = ex

  sdf.to_excel(writer, sheet_name = str(ex.StudyID))

  # the PESI dicom directories contain on dummy dicom headers for the LM files
  # we have to check whether the actual LM files (BLF files exist in petLists)
  ldf                              = check_exam_LM_files(study_data_frames[ex.StudyID])
  listmode_data_frames[ex.StudyID] = ldf

  ldf.to_excel(writer, sheet_name = f'{ex.StudyID}_LM')

writer.save()
#----------------------------------------------------------------------------------------------
