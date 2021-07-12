import os
import re
import cv2
import pandas as pd
from tqdm import tqdm
import numpy as np
import math as ms
import tifffile as tiff
import imagej
from skimage import io
from skimage.morphology import disk, erosion, dilation, white_tophat, reconstruction
from skimage.measure import label, regionprops_table
from astropy.convolution import RickerWavelet2DKernel
from PIL import Image
from scipy import ndimage
from scipy.stats import norm
from scipy.ndimage import filters


class SimPullAnalysis:

    def __init__(self, data_path):

        self.error = 1 # When this value is 1, no error was detected in the object.
        self.path_program = os.path.dirname(__file__)
        self.path_data_main = data_path

        # Construct dirs for results
        self.path_result_main = data_path + '_results'
        if os.path.isdir(self.path_result_main) != 1:
            os.mkdir(self.path_result_main)
        self.path_result_raw = os.path.join(self.path_result_main, 'raw')
        if os.path.isdir(self.path_result_raw) != 1:
            os.mkdir(self.path_result_raw)
        self.path_result_samples = os.path.join(self.path_result_main, 'samples')
        if os.path.isdir(self.path_result_samples) != 1:
            os.mkdir(self.path_result_samples)
        naming_system = self.gather_project_info()
        if naming_system == 0:
            self.error = 'Invalid naming system for images. Currently supported naming systems are: XnYnRnWnCn, XnYnRnWn and Posn.'


    def gather_project_info(self):

        self.fov_paths = {} # dict - FoV name: path to the corresponding image
        for root, dirs, files in os.walk(self.path_data_main):
            for file in files:
                if file.endswith(".tif"):
                    try:
                        pos = re.findall(r"X\dY\dR\dW\dC\d", file)[-1]
                        naming_system = 'XnYnRnWnCn'
                    except IndexError:
                        try:
                            pos = re.findall(r'X\dY\dR\dW\d', file)[-1]
                            naming_system = 'XnYnRnWn'
                        except IndexError:
                            try:
                                pos = re.findall(r'Pos\d', file)[-1]
                                naming_system = 'Posn'
                            except IndexError:
                                return 0
                    self.fov_paths[pos] = os.path.join(root, file)
        self.wells = {} # dict - well name: list of FoV taken in the well
        try:
            list(self.fov_paths.keys())[0][7] # Check if the naming system is in 'pos\d'. IndexError would be raised if so.
            pass
        except IndexError:
            for fov in self.fov_paths:
                self.wells[fov] = [fov]
            return naming_system

        for fov in self.fov_paths:
            if fov[:4] in self.wells:
                self.wells[fov[:4]] += [fov]
            else:
                self.wells[fov[:4]] = [fov]
        return naming_system


    def call_ComDet(self, size, threshold, progress_signal=None, IJ=None):

        if progress_signal == None: #i.e. running in non-GUI mode
            path_fiji = os.path.join(self.path_program, 'Fiji.app')
            IJ = imagej.init(path_fiji, headless=False)
            IJ.ui().showUI()
            workload = tqdm(sorted(self.fov_paths)) # using tqdm as progress bar in cmd
        else:
            workload = sorted(self.fov_paths)
            c = 1 # progress indicator

        #Check if the images are stack, and choose correct macro
        test_img = io.imread(list(self.fov_paths.values())[0])
        if len(test_img.shape) == 3: 
            stacked = True
        else:
            stacked = False

        for field in workload:
            imgFile = self.fov_paths[field]
            saveto = os.path.join(self.path_result_raw, field)
            saveto = saveto.replace("\\", "/")
            img = IJ.io().open(imgFile)
            IJ.ui().show(field, img)

            if stacked:
                macro = """
                run("Z Project...", "projection=[Average Intensity]");
                run("Detect Particles", "ch1i ch1a="""+str(size)+""" ch1s="""+str(threshold)+""" rois=Ovals add=Nothing summary=Reset");
                selectWindow('Results');
                saveAs("Results", \""""+saveto+"""_results.csv\");
                close("Results");
                selectWindow('Summary');
                saveAs("Results", \""""+saveto+"""_summary.txt\");
                close(\""""+field+"""_summary.txt\");
                selectWindow(\"AVG_"""+field+"""\");
                saveAs("tif", \""""+saveto+""".tif\");
                close();
                close();
                """
                IJ.py.run_macro(macro)
            else:
                macro = """
                run("Detect Particles", "ch1i ch1a="""+str(size)+""" ch1s="""+str(threshold)+""" rois=Ovals add=Nothing summary=Reset");
                selectWindow('Results');
                saveAs("Results", \""""+saveto+"""_results.csv\");
                close("Results");
                selectWindow('Summary');
                saveAs("Results", \""""+saveto+"""_summary.txt\");
                close(\""""+field+"""_summary.txt\");
                selectWindow(\""""+field+"""\");
                saveAs("tif", \""""+saveto+""".tif\");
                close();
                """
                IJ.py.run_macro(macro)

            if progress_signal == None:
                pass
            else:
                progress_signal.emit(c)
                c += 1

        if progress_signal == None:
            IJ.py.run_macro("""run("Quit")""")
        else:
            IJ.py.run_macro("""
                if (isOpen("Log")) {
                 selectWindow("Log");
                 run("Close" );
                }
                """)

        return 1


    def call_Trevor(self, bg_thres = 1, tophat_disk_size=10, progress_signal=None, erode_size = 1):
        if progress_signal == None: #i.e. running in non-GUI mode
            workload = tqdm(sorted(self.fov_paths)) # using tqdm as progress bar in cmd
        else:
            workload = sorted(self.fov_paths)
            c = 1 # progress indicator

        for field in workload:
            imgFile = self.fov_paths[field]
            saveto = os.path.join(self.path_result_raw, field)
            saveto = saveto.replace("\\", "/")
            img = io.imread(imgFile) # Read image
            img = img.astype(np.float64)
            if len(img.shape) == 3: # Determine if the image is a stack file with multiple slices
                img = np.mean(img, axis=0) # If true, average the image
            else:
                pass # If already averaged, go on processing

            img_size = np.shape(img)
            tophat_disk_size = 50
            tophat_disk = disk(tophat_disk_size) # create tophat structural element disk, diam = tophat_disk_size (typically set to 10)
            tophat_img = white_tophat(img, tophat_disk) # Filter image with tophat
            kernelsize = 1
            ricker_2d_kernel = RickerWavelet2DKernel(kernelsize)
            
            def convolve2D(image, kernel, padding=4, strides=1):
                
                # Cross Correlation
                kernel = np.flipud(np.fliplr(kernel))
            
                # Gather Shapes of Kernel + Image + Padding
                xKernShape = kernel.shape[0]
                yKernShape = kernel.shape[1]
                xImgShape = image.shape[0]
                yImgShape = image.shape[1]
            
                # Shape of Output Convolution
                xOutput = int(((xImgShape - xKernShape + 2 * padding) / strides) + 1)
                yOutput = int(((yImgShape - yKernShape + 2 * padding) / strides) + 1)
                output = np.zeros((xOutput, yOutput))
            
                # Apply Equal Padding to All Sides
                if padding != 0:
                    imagePadded = np.zeros((image.shape[0] + padding*2, image.shape[1] + padding*2))
                    imagePadded[int(padding):int(-1 * padding), int(padding):int(-1 * padding)] = image
                    #print(imagePadded)
                else:
                    imagePadded = image
            
                # Iterate through image
                for y in range(image.shape[1]):
                    # Exit Convolution
                    if y > image.shape[1] - yKernShape:
                        break
                    # Only Convolve if y has gone down by the specified Strides
                    if y % strides == 0:
                        for x in range(image.shape[0]):
                            # Go to next row once kernel is out of bounds
                            if x > image.shape[0] - xKernShape:
                                break
                            try:
                                # Only Convolve if x has moved by the specified Strides
                                if x % strides == 0:
                                    output[x, y] = (kernel * imagePadded[x: x + xKernShape, y: y + yKernShape]).sum()
                            except:
                                break
            
                return output
            output = convolve2D(tophat_img, ricker_2d_kernel, padding=0)
            out_img = Image.fromarray(output)
            out_resize = out_img.resize(img_size)
            out_array = np.array(out_resize) 
            mu,sigma = norm.fit(out_array)
            threshold = mu + bg_thres*sigma
            out_array[out_array<threshold] = 0
            
            erode_img = erosion(out_array, disk(erode_size))
            dilate_img = dilation(erode_img, disk(erode_size))
            dilate_img[dilate_img>0] = 1
            mask = np.copy(dilate_img)
            
            io.imsave(saveto + '.tif', mask) # save masked image as result
            
            inverse_mask = 1-mask
            img_bgonly = inverse_mask*img
            seed_img = np.copy(img_bgonly) #https://scikit-image.org/docs/dev/auto_examples/features_detection/plot_holes_and_peaks.html
            seed_img[1:-1, 1:-1] = img_bgonly.max()
            seed_mask = img_bgonly
            filled_img = reconstruction(seed_img, seed_mask, method='erosion')
            img_nobg = abs(img - filled_img)

            # Label the image to index all aggregates
            labeled_img = label(mask)
            # *save image

            intensity_list = []
            Abs_frame = []
            Channel = []
            Slice = []
            Frame = []

            # Get the number of particles
            num_aggregates = int(np.max(labeled_img))
            # Get profiles of labeled image
            df = regionprops_table(labeled_img, intensity_image=img, properties=['label', 'area', 'centroid', 'bbox'])
            df = pd.DataFrame(df)
            df.columns = [' ', 'NArea', 'X_(px)', 'Y_(px)', 'xMin', 'yMin', 'xMax', 'yMax']
            # Analyze each particle for integra
            for j in range(0, num_aggregates):
                current_aggregate = np.copy(labeled_img)
                current_aggregate[current_aggregate != j + 1] = 0
                current_aggregate[current_aggregate > 0] = 1
                intensity = np.sum(current_aggregate * img_nobg)
                intensity_list.append(intensity)
                
                Abs_frame.append(1)
                Channel.append(1)
                Slice.append(1)
                Frame.append(1)

            df['Abs_frame'] = Abs_frame
            df['Channel']= Channel
            df['Slice'] = Slice
            df['Frame'] = Frame
            df['IntegratedInt'] = intensity_list

            df.to_csv(saveto + '_results.csv', index=False) # save result.csv

            if progress_signal == None:
                pass
            else:
                progress_signal.emit(c)
                c += 1
        return 1


    def generate_reports(self, progress_signal=None):
        if progress_signal == None: #i.e. running in non-GUI mode
            workload = tqdm(sorted(self.wells)) # using tqdm as progress bar in cmd
        else:
            workload = sorted(self.wells)
            c = 1 # progress indicator
        # Generate sample reports
        for well in workload:
            well_result = pd.DataFrame()
            for fov in self.wells[well]:
                try:
                    df = pd.read_csv(self.path_result_raw + '/' + fov + '_results.csv')
                    df = df.drop(columns=[' ', 'Channel', 'Slice', 'Frame'])
                    df['FoV'] = fov
                    df['IntPerArea'] = df.IntegratedInt / df.NArea
                    well_result = pd.concat([well_result, df])
                except pd.errors.EmptyDataError:
                    pass
            well_result.to_csv(self.path_result_samples + '/' + well + '.csv', index=False)
            if progress_signal == None:
                pass
            else:
                progress_signal.emit(c)
                c += 1

        # Generate summary report
        summary_report = pd.DataFrame()
        for well in workload:
            try:
                df = pd.read_csv(self.path_result_samples + '/' + well + '.csv')
                df_sum = pd.DataFrame.from_dict({
                    'Well': [well],
                    'NoOfFoV': [len(self.wells[well])],
                    'ParticlePerFoV': [len(df.index) / len(self.wells[well])],
                    'MeanSize': [df.NArea.mean()],
                    'MeanIntegrInt': [df.IntegratedInt.mean()],
                    'MeanIntPerArea': [df.IntPerArea.mean()]
                })
                summary_report = pd.concat([summary_report, df_sum])
            except pd.errors.EmptyDataError:
                pass
            if progress_signal == None:
                pass
            else:
                progress_signal.emit(c)
                c += 1
        summary_report.to_csv(self.path_result_main + '/Summary.csv', index=False)

        # Generate quality control report
        QC_data = pd.DataFrame()
        for well in workload:
            try:
                df = pd.read_csv(self.path_result_samples + '/' + well + '.csv')
                df['Well'] = well
                df = df[['Well','FoV', 'NArea', 'IntegratedInt', 'IntPerArea']]
                QC_data = pd.concat([QC_data, df])
            except pd.errors.EmptyDataError:
                pass
            if progress_signal == None:
                pass
            else:
                progress_signal.emit(c)
                c += 1
        QC_data = QC_data.reset_index(drop=True)
        QC_data.to_csv(self.path_result_main + '/QC.csv', index=False)
        
        return 1



class LiposomeAssayAnalysis:

    def __init__(self, data_path):
        self.error = 1 # When this value is 1, no error was detected in the object.
        self.path_program = os.path.dirname(__file__)
        self.path_data_main = data_path

        # Construct dirs for results
        self.path_result_main = data_path + '_results'
        if os.path.isdir(self.path_result_main) != 1:
            os.mkdir(self.path_result_main)
        self.path_result_raw = os.path.join(self.path_result_main, 'raw')
        if os.path.isdir(self.path_result_raw) != 1:
            os.mkdir(self.path_result_raw)
        self.gather_project_info()


    def gather_project_info(self):
        samples = [name for name in os.listdir(self.path_data_main) if not name.startswith('.') and name != 'results']
        if 'Ionomycin' in samples:
            self.samples = [self.path_data_main]
        else:
            self.samples = [os.path.join(self.path_data_main, sample) for sample in samples]

        ### Create result directory
        for sample in self.samples:
            if not os.path.isdir(sample.replace(self.path_data_main, self.path_result_raw)):
                os.mkdir((sample.replace(self.path_data_main, self.path_result_raw)))

    
    def run_analysis(self, threshold, progress_signal=None, log_signal=None):

        def extract_filename(path):
            """
            walk through a directory and put names of all tiff files into an ordered list
            para: path - string
            return: filenames - list of string 
            """

            filenames = []
            for root, dirs, files in os.walk(path):
                for name in files:
                    if name.endswith('.tif'):
                        filenames.append(name)
            filenames = sorted(filenames)
            return filenames


        def average_frame(path):
            """
            input 'path' for stacked tiff file and the 'number of images' contained
            separate individual images from a tiff stack.
            para: path - string
            return: ave_img - 2D array
            """

            ori_img = tiff.imread(path)
            ave_img = np.mean(ori_img, axis=0)
            ave_img = ave_img.astype('uint16')

            return ave_img


        def img_alignment(Ionomycin, Sample, Blank):
            """
            image alignment based on cross-correlation
            Ionomycin image is the reference image
            para: Ionomycin, Sample, Blank - 2D array
            return: Corrected_Sample, Corrected_Blank - 2D array
            """

            centre_ = (Ionomycin.shape[0]/2, Ionomycin.shape[1]/2)
            # 2d fourier transform of averaged images
            FIonomycin = np.fft.fft2(Ionomycin)
            FSample = np.fft.fft2(Sample)
            FBlank = np.fft.fft2(Blank)

            # Correlation based on Ionomycin image
            FRIS = FIonomycin*np.conj(FSample)
            FRIB = FIonomycin*np.conj(FBlank)

            RIS = np.fft.ifft2(FRIS)
            RIS = np.fft.fftshift(RIS)
            RIB = np.fft.ifft2(FRIB)
            RIB = np.fft.fftshift(RIB)

            [i, j] = np.where(RIS == RIS.max())
            [g, k] = np.where(RIB == RIB.max())

            # offset values
            IS_x_offset = i-centre_[1]
            IS_y_offset = j-centre_[0]
            IB_x_offset = g-centre_[1]
            IB_y_offset = k-centre_[0]

            # Correction
            MIS = np.float64([[1, 0, IS_y_offset], [0, 1, IS_x_offset]])
            Corrected_Sample = cv2.warpAffine(Sample, MIS, Ionomycin.shape)
            MIB = np.float64([[1, 0, IB_y_offset], [0, 1, IB_x_offset]])
            Corrected_Blank = cv2.warpAffine(Blank, MIB, Ionomycin.shape)

            return Corrected_Sample, Corrected_Blank


        def peak_locating(data, threshold):
            """
            Credit to Dr Daniel R Whiten
            para: data - 2D array
            para: threshold - integer
            return: xy_thresh - 2D array [[x1, y1], [x2, y2]...]
            """

            data_max = filters.maximum_filter(data, 3)
            maxima = (data == data_max)
            data_min = filters.minimum_filter(data, 3)
            diff = ((data_max - data_min) > threshold)
            maxima[diff == 0] = 0

            labeled, num_objects = ndimage.label(maxima)
            xy = np.array(ndimage.center_of_mass(data, labeled, range(1, num_objects+1)))
            xy_thresh = np.zeros((0, 2))
            for row in xy:
                a = row[0]
                b = row[1]
                if (a > 30) and (a < 480) and (b > 30) and (b < 480):
                    ab = np.array([np.uint16(a), np.uint16(b)])
                    xy_thresh = np.vstack((xy_thresh, ab))
            xy_thresh = xy_thresh[1:] 

            return xy_thresh


        def intensities(image_array, peak_coor, radius=3):
            """
            When the local peak is found, extract all the coordinates of pixels in a 'radius'
            para: image_array - 2D array
            para: peak_coor - 2D array [[x1, y1], [x2, y2]]
            para: radius - integer
            return: intensities - 2D array [[I1], [I2]]
            """

            x_ind, y_ind = np.indices(image_array.shape)
            intensities = np.zeros((0,1))
            for (x, y) in peak_coor:
                intensity = 0
                circle_points = ((x_ind - x)**2 + (y_ind - y)**2) <= radius**2
                coor = np.where(circle_points == True)
                coor = np.array(list(zip(coor[0], coor[1])))
                for j in coor:
                    intensity += image_array[j[0], j[1]]
                intensities = np.vstack((intensities, intensity))

            return intensities


        def influx_qc(field, peaks, influx_df):
            ### Remove error measurements ###
            """ 
            if 100% < influx < 110% take as 100%
            if -10% < influx < 0% take as 0
            if influx calculated to be nan or <-10% or >110% count as error
            """ 
            influx_df['Influx'] = [100 if i >= 100 and i <= 110 else i for i in influx_df['Influx']]
            influx_df['Influx'] = [0 if i <= 0 and i >= -10 else i for i in influx_df['Influx']]
            influx_df['Influx'] = ['error' if ms.isnan(np.float(i)) or i < -10 or i > 110 else i for i in influx_df['Influx']]

            ### Generate a dataframe which contains the result of current FoV ###
            field_result = pd.concat([
                pd.DataFrame(np.repeat(field, len(peaks)), columns=['Field']),
                pd.DataFrame(peaks, columns=['X', 'Y']),
                influx_df
                ],axis = 1)

            ### Filter out error data ###
            field_result = field_result[field_result.Influx != 'error']
            
            ### Get field summary ###
            try:
                field_error = (influx_df.Influx.values == 'error').sum()
            except AttributeError:
                field_error = 0

            field_summary = pd.DataFrame({
                "FoV": field,
                "Mean influx": field_result.Influx.mean(),
                "Total liposomes": len(peaks),
                "Valid liposomes": len(peaks)-field_error,
                "Invalid liposomes": field_error
                })
            return field_result, field_summary


        def pass_log(text):
            if log_signal == None:
                print(text)
            else:
                log_signal.emit(text)


        if progress_signal == None: #i.e. running in non-GUI mode
            workload = tqdm(sorted(self.samples)) # using tqdm as progress bar in cmd
        else:
            workload = sorted(self.samples)
            c = 1 # progress indicator

        for sample in workload:
            sample_summary = pd.DataFrame()

            # report which sample is running to log window
            pass_log('Running sample: ' + sample)
            
            ionomycin_path = os.path.join(sample, 'Ionomycin')
            sample_path = os.path.join(sample, 'Sample')
            blank_path = os.path.join(sample, 'Blank')

            if not os.path.isdir(ionomycin_path):
                pass_log('Skip ' + sample + '. No data found in the sample folder.')

            ### Obtain filenames for fields of view ###
            field_names = extract_filename(ionomycin_path)

            for c, field in enumerate(field_names, 1):
                ### Average tiff files ###
                ionomycin_mean = average_frame(os.path.join(ionomycin_path, field))
                sample_mean = average_frame(os.path.join(sample_path, field))
                blank_mean = average_frame(os.path.join(blank_path, field))
                
                ### Align blank and sample images to the ionomycin image ###
                sample_aligned, blank_aligned = img_alignment(ionomycin_mean, sample_mean, blank_mean)

                ### Locate the peaks on the ionomycin image ###
                peaks = peak_locating(ionomycin_mean, threshold)
                
                if len(peaks) == 0:
                    pass_log('Field ' + field + ' of sample ' + sample +' ignored due to no liposome located in this FoV.')
                    field_summary = pd.DataFrame({
                        "FoV": field,
                        "Mean influx": 0,
                        "Total liposomes": 0,
                        "Valid liposomes": 0,
                        "Invalid liposomes": 0
                        })
                    sample_summary = pd.concat([sample_summary, field_summary])
                else:
                    ### Calculate the intensities of peaks with certain radius (in pixel) ###
                    ionomycin_intensity = intensities(ionomycin_mean, peaks)
                    sample_intensity = intensities(sample_aligned, peaks)
                    blank_intensity = intensities(blank_aligned, peaks)

                    ### Calculate influx of each single liposome and count errors ###
                    influx_df = pd.DataFrame((sample_intensity - blank_intensity)/(ionomycin_intensity - blank_intensity)*100, columns=['Influx'])

                    field_result, field_summary = influx_qc(field, peaks, influx_df)
                    field_result.to_csv(os.path.join(sample.replace(self.path_data_main, self.path_result_raw), field+".csv"))

                    sample_summary = pd.concat([sample_summary, field_summary])
            sample_summary.to_csv(sample.replace(self.path_data_main, self.path_result_raw) + ".csv")



if __name__ == "__main__":

    path = input('Please input the path for analysis:\n')
    if os.path.isdir(path) != True:
    	print('Please input valid directory for data.')
    	quit()
    project = SimPullAnalysis(path)
    print('Launching: ' + path)
    size = input('Please input the estimated size of particles(in pixels):\n')
    threshold = input('Please input the threshold to apply(in nSD):\n')
    print('Picking up particles in Fiji...')
    project.call_ComDet(size=size, threshold=threshold)
    print('Generating reports...')
    project.generate_reports()
    print('Done.')



