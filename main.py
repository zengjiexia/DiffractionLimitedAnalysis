import sys
import os

import PySide6
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QMessageBox, QProgressDialog, QFileDialog, QVBoxLayout, QRadioButton, QButtonGroup
from PySide6.QtCore import QFile, QIODevice, Slot, Qt, QThread, Signal, QRect
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QIcon
import pyqtgraph as pg
import toolbox
from logics import SimPullAnalysis, LiposomeAssayAnalysis, SuperResAnalysis
import pandas as pd
import numpy as np
import imagej
import scyjava
import json
plugins_dir = os.path.join(os.path.dirname(__file__), 'Fiji.app/plugins')
scyjava.config.add_option(f'-Dplugins.dir={plugins_dir}')
pg.setConfigOption('background', 'w')

class MainWindow(QMainWindow):

    def __init__(self):
        super(MainWindow, self).__init__()
        self.loadUI()


    def loadUI(self):

        path = os.path.join(os.path.dirname(__file__), "UI_form/MainWindow.ui")
        ui_file = QFile(path)
        if not ui_file.open(QIODevice.ReadOnly):
            print(f"Cannot open {ui_file_name}: {ui_file.errorString()}")
            sys.exit(-1)

        class UiLoader(QUiLoader): # Enable promotion to custom widgets
            def createWidget(self, className, parent=None, name=""):
                #if className == "PlotWidget":
                #    return pg.PlotWidget(parent=parent) # promote to pyqtgraph.PlotWidget
                if className == "LogTextEdit":
                    return toolbox.LogTextEdit(parent=parent) # promote to self defined LogTextEdit(QPlainTextEdit)
                return super().createWidget(className, parent, name)

        loader = UiLoader()
        self.window = loader.load(ui_file, self)

        self.path_fiji = os.path.join(os.path.dirname(__file__), 'Fiji.app')
        self.IJ = imagej.init(self.path_fiji, headless=False)

        # Menu
            # File
        self.window.actionLoad.triggered.connect(self.loadDataPath)
            # Tools
        self.window.actionRun_analysis_DFLSP.triggered.connect(self.clickDFLSPRun)
        self.window.actionGenerate_reports_DFLSP.triggered.connect(self.clickDFLSPGenerateReports)
        self.window.actionRead_tagged_results_DFLSP.triggered.connect(self.clickDFLSPReadTaggedResults)

        self.window.actionRun_analysis_LipoAssay.triggered.connect(self.clickLipoAssayRun)
        self.window.actionGenerate_report_LipoAssay.triggered.connect(self.clickLipoAssayGenerateReport)
            # Help
        self.window.actionComDet.triggered.connect(self.helpComDet)
        self.window.actionTrevor.triggered.connect(self.helpTrevor)
        self.window.actionProgram_frozen.triggered.connect(self.helpFrozen)

        # DFLSP window widgets
        self.window.DFLSP_runButton.clicked.connect(self.clickDFLSPRun)
        self.window.DFLSP_tagButton.clicked.connect(self.clickDFLSPTag)
        self.window.DFLSP_oaButton.clicked.connect(self.clickDFLSPOA)

        # LipoAssay window widgets
        self.window.LipoAssay_runButton.clicked.connect(self.clickLipoAssayRun)

        # SR window widgets
        self.window.SupRes_runReconstructionButton.clicked.connect(self.clickSRRun)
        self.window.SupRes_methodSelector.currentIndexChanged.connect(self._methodOptSR)
        self.window.SupRes_FidCorrMethodSelector.currentIndexChanged.connect(self._methodOptSRFidCorr)
        self.window.SupRes_loadButton.clicked.connect(self.clickLoadSRPreviousAttempts)
        self.window.SupRes_previousReconstructionAttemptSelector.currentIndexChanged.connect(self._SRPreviousReconstructionAttemptSelected)
        self.window.SupRes_runFidCorrButton.clicked.connect(self.clickSRfidCorr)
        self.window.SupRes_previousCorrectionAttemptsSelector.currentIndexChanged.connect(self._SRPreviousCorrectionAttemptSelected)

        ui_file.close()
        if not self.window:
            print(loader.errorString())
            sys.exit(-1)
        self.window.show()
        sys.exit(app.exec_())


    def updateLog(self, message):
        self.window.main_logBar.insertPlainText(message + '\n')
        self.window.main_logBar.verticalScrollBar().setValue(
            self.window.main_logBar.verticalScrollBar().maximum()) # auto scroll down to the newest message


    def initialiseProgress(self, work, workload):
        self.window.progressBar.setMaximum(workload)
        self.window.progressBar.setValue(0)
        self.window.progressBarLabel.setText(work)


    def updateProgress(self, progress):
        self.window.progressBar.setValue(progress)


    def restProgress(self):
        self.window.progressBarLabel.setText('No work in process.')
        self.window.progressBar.reset()


    def showMessage(self, msg_type, message):
        msgBox = QMessageBox(self.window)
        if msg_type == 'c':
            msgBox.setIcon(QMessageBox.Critical)
            msgBox.setWindowTitle('Critical Error')
        elif msg_type == 'w':
            msgBox.setIcon(QMessageBox.Warning)
            msgBox.setWindowTitle('Warning')
        elif msg_type == 'i':
            msgBox.setIcon(QMessageBox.Information)
            msgBox.setWindowTitle('Information')
        msgBox.setText(message)
        returnValue = msgBox.exec_()


    def loadDataPath(self):
        data_path = QFileDialog.getExistingDirectory(parent=self.window, caption='Browse path for data.', dir=os.path.dirname(__file__))
        self.window.DFLSP_pathEntry.setText(data_path)
        self.window.LipoAssay_pathEntry.setText(data_path)
        #* set all paths

    # Diffraction Limited SiMPull Analysis
    def clickDFLSPRun(self):
        guard = self._checkDFLSPParameters()
        if guard == 1:
            guard = self._runDFLSPAnalysis()


    def clickDFLSPGenerateReports(self):
        data_path = self.window.DFLSP_pathEntry.text()
        self.data_path = data_path.replace('_results', '')
        self.window.DFLSP_pathEntry.setText(self.data_path)
        guard = self._checkDFLSPParameters()
        if guard == 1:
            if os.path.isdir(self.data_path + '_results') ==False:
                self.showMessage('w', 'This dataset has not been analysed. Please run analysis.')
            else:

                self.updateLog('Data path set to '+data_path)
                self._generateDFLSPReports()


    def clickDFLSPReadTaggedResults(self):
        data_path = self.window.DFLSP_pathEntry.text()
        self.data_path = data_path.replace('_results', '')
        self.window.DFLSP_pathEntry.setText(self.data_path)
        guard = self._checkDFLSPParameters()
        if guard == 1:
            if os.path.isdir(self.data_path + '_results') ==False:
                self.showMessage('w', 'This dataset has not been analysed. Please run analysis.')
            else:
                self.updateLog('Data path set to '+data_path)
                self._showDFLSPResult()
                self.window.DFLSP_tagButton.setEnabled(True)
                self.window.DFLSP_oaButton.setEnabled(True)


    def _checkDFLSPParameters(self):
        # Check if data path exists
        data_path = self.window.DFLSP_pathEntry.text()
        if os.path.isdir(data_path) == False:
            self.showMessage('w', 'Path to folder not found.')
            return 0
        else:
            self.data_path = data_path
            self.window.DFLSP_pathEntry.setText(self.data_path)
            self.updateLog('Data path set to '+data_path)

        # Check input: threshold
        try:
            self.threshold = int(self.window.DFLSP_thresholdEntry.text())
            self.window.DFLSP_thresholdEntry.setText(str(self.threshold))
        except ValueError:
            self.showMessage('c', 'Please input a number for threshold.')
            return 0
        if self.threshold <= 2 or self.threshold >= 20:
            self.updateLog('Threshold set as '+str(self.threshold)+' SD. Suggested range would be 3-20 SD.')
        else:
            self.updateLog('Threshold set at '+str(self.threshold)+' SD.')

        # Check input: estimated size
        try:
            self.size = int(self.window.DFLSP_sizeEntry.text())
            self.window.DFLSP_sizeEntry.setText(str(self.size))
        except ValueError:
            self.showMessage('c', 'Please input a number for estimated particle size.')
            return 0
        if self.size >= 15:
            self.updateLog('Estimated particle size set as '+str(self.size)+' pixels which is quite high. Pariticles close to each other might be considered as one.')
        else:
            self.updateLog('Estimated particle size set as '+str(self.size)+' pixels.')

        self.project = SimPullAnalysis(self.data_path) # Creat SimPullAnalysis object
        if self.project.error == 1:
            return 1
        else:
            self.showMessage('c', self.project.error)


    def _runDFLSPAnalysis(self):
        self.initialiseProgress('Locating particles...', len(self.project.fov_paths))

        # Create a QThread object
        self.PFThread = QThread()
        # Create a worker object
        self.particleFinder = toolbox.DFLParticleFinder(self.window.DFLSP_methodSelector.currentText(), self.project, self.size, self.threshold, self.IJ)

        # Connect signals and slots
        self.PFThread.started.connect(self.particleFinder.run)
        self.particleFinder.finished.connect(self.PFThread.quit)
        self.particleFinder.finished.connect(self.particleFinder.deleteLater)
        self.PFThread.finished.connect(self.PFThread.deleteLater)
        # Move worker to the thread
        self.particleFinder.moveToThread(self.PFThread)
        # Connect progress signal to GUI
        self.particleFinder.progress.connect(self.updateProgress)
        # Start the thread
        self.PFThread.start()
        self.updateLog('Start to locate particles...')
        
        # UI response
        self.window.DFLSP_runButton.setEnabled(False) # Block 'Run' button
        self.PFThread.finished.connect(
            lambda: self.window.DFLSP_runButton.setEnabled(True) # Reset 'Run' button
            )
        self.PFThread.finished.connect(
            lambda: self.updateLog('Particles in images are located.')
            )
        self.PFThread.finished.connect(
            lambda: self.restProgress()
            ) # Reset progress bar to rest
        try:
            self.PFThread.finished.connect(
                lambda: self._generateDFLSPReports()
                ) # Generate reports
        except:
            print(sys.exc_info())


    def _generateDFLSPReports(self):
        self.initialiseProgress('Generating reports...', 3*len(self.project.wells))

        # Generate sample summaries, Summary.csv and QC.csv
        self.reportThread = QThread()
        self.reportWriter = toolbox.ReportWriter(self.project)

        self.reportThread.started.connect(self.reportWriter.run)
        self.reportWriter.finished.connect(self.reportThread.quit)
        self.reportWriter.finished.connect(self.reportWriter.deleteLater)
        self.reportThread.finished.connect(self.reportThread.deleteLater)


        self.reportWriter.moveToThread(self.reportThread)

        self.reportWriter.progress.connect(self.updateProgress)

        self.reportThread.start()
        self.updateLog('Start to generate reports...')

        self.window.DFLSP_runButton.setEnabled(False) # Block 'Run' button
        self.reportThread.finished.connect(
            lambda: self.window.DFLSP_runButton.setEnabled(True) # Reset 'Run' button
            )
        self.reportThread.finished.connect(
            lambda: self.window.DFLSP_tagButton.setEnabled(True)
            )
        self.reportThread.finished.connect(
            lambda: self.updateLog('Reports generated at: ' + self.project.path_result_main)
            )
        self.reportThread.finished.connect(
            lambda: self.restProgress()
            ) # Reset progress bar to rest
        try:
            self.reportThread.finished.connect(
                lambda: self._showDFLSPResult()
                )
        except:
            print(sys.exc_info())


    def _showDFLSPResult(self):
        df = pd.read_csv(self.project.path_result_main + '/Summary.csv')
        model = toolbox.PandasModel(df)
        self.window.DFLSP_resultTable.setModel(model)


    def clickDFLSPTag(self):
        self.tagdatapopup = TagDataPopup(parent=self)
        self.tagdatapopup.window.show()
        self.tagdatapopup.finished.connect(
            lambda: self._showDFLSPResult()
            )
        self.tagdatapopup.finished.connect(self.tagdatapopup.window.close)
        self.tagdatapopup.finished.connect(
            lambda: self.updateLog('Tagged data saved at: ' + self.project.path_result_main)
            )
        self.tagdatapopup.finished.connect(
            lambda: self.window.DFLSP_oaButton.setEnabled(True)
            )
        

    def clickDFLSPOA(self):
        self.groupingpopup = GroupingPopup(parent=self)
        self.groupingpopup.window.show()
        self.groupingpopup.output.connect(self._oaProcess)
        self.groupingpopup.finished.connect(self.groupingpopup.window.close)


    def _oaProcess(self, experimentSelection, xaxisSelection):
        df = pd.read_csv(self.project.path_result_main + '/QC.csv')
        if experimentSelection == 'None':
            self.oapopup = OrthogonalAnalysisPopup(task='All', df=df, xaxis=xaxisSelection, parent=self)
            self.oapopup.window.show()
            self.oapopup.finished.connect(self.oapopup.window.close)
        else:
            tasks = list(df[experimentSelection].unique())
            for t in tasks:
                t_df = df.loc[df[experimentSelection] == t]
                self.oapopup = OrthogonalAnalysisPopup(task=t, df=t_df, xaxis=xaxisSelection, parent=self)
                self.oapopup.window.show()
                self.oapopup.finished.connect(self.oapopup.window.close)


    # Liposome Assay Analysis
    def clickLipoAssayRun(self):
        guard = self._checkLipoAssayParameters()
        if guard == 1:
            guard = self._runLipoAssayAnalysis()


    def clickLipoAssayGenerateReport(self):
        data_path = self.window.LipoAssay_pathEntry.text()
        self.data_path = data_path.replace('_results', '')
        self.window.LipoAssay_pathEntry.setText(self.data_path)
        guard = self._checkLipoAssayParameters()
        if guard == 1:
            if os.path.isdir(self.data_path + '_results') ==False:
                self.showMessage('w', 'This dataset has not been analysed. Please run analysis.')
            else:
                self.updateLog('Data path set to '+data_path)
                self._generateLipoAssayReports()


    def _checkLipoAssayParameters(self):
        #Check if data path exists
        data_path = self.window.LipoAssay_pathEntry.text()
        if os.path.isdir(data_path) == False:
            self.showMessage('w', 'Path to folder not found.')
            return 0
        else:
            self.data_path = data_path
            self.window.LipoAssay_pathEntry.setText(self.data_path)
            self.updateLog('Data path set to '+data_path)

        #Check input: threshold
        try:
            self.threshold = int(self.window.LipoAssay_thresholdEntry.text())
            self.window.LipoAssay_thresholdEntry.setText(str(self.threshold))
        except ValueError:
            self.showMessage('c', 'Please input a number for threshold.')
            return 0
        if self.threshold <= 20 or self.threshold >= 160:
            self.updateLog('Threshold set as '+str(self.threshold)+'. Suggested range would be 20-160.')
        else:
            self.updateLog('Threshold set at '+str(self.threshold)+'.')

        self.project = LiposomeAssayAnalysis(self.data_path) # Create project for liposome assay analysis
        return 1


    def _runLipoAssayAnalysis(self):
        self.initialiseProgress('Analysing liposomes...', len(self.project.samples))

        # Create a QThread object
        self.lipoThread = QThread()
        # Create a worker object
        self.lipoWorker = toolbox.LipoAssayWorker(self.project, self.threshold)

        # Connect signals and slots
        self.lipoThread.started.connect(self.lipoWorker.run)
        self.lipoWorker.finished.connect(self.lipoThread.quit)
        self.lipoWorker.finished.connect(self.lipoWorker.deleteLater)
        self.lipoThread.finished.connect(self.lipoThread.deleteLater)
        # Move worker to the thread
        self.lipoWorker.moveToThread(self.lipoThread)
        # Connect progress signal to GUI
        self.lipoWorker.progress.connect(self.updateProgress)
        self.lipoWorker.log.connect(self.updateLog)
        # Start the thread
        self.lipoThread.start()
        self.updateLog('Start to locate particles...')
        
        # UI response
        self.window.LipoAssay_runButton.setEnabled(False) # Block 'Run' button
        self.lipoThread.finished.connect(
            lambda: self.window.LipoAssay_runButton.setEnabled(True) # Reset 'Run' button
            )
        self.lipoThread.finished.connect(
            lambda: self.updateLog('Liposome analysis finished.')
            )
        self.lipoThread.finished.connect(
            lambda: self.restProgress()
            ) # Reset progress bar to rest
        try:
            self.lipoThread.finished.connect(
                lambda: self._generateLipoAssayReports()
                ) # Generate reports
        except:
            print(sys.exc_info())


    def _generateLipoAssayReports(self):
        self.initialiseProgress('Generating reports...', len(self.project.samples))

        # Generate Summary.csv
        self.reportThread = QThread()
        self.reportWriter = toolbox.ReportWriter(self.project)

        self.reportThread.started.connect(self.reportWriter.run)
        self.reportWriter.finished.connect(self.reportThread.quit)
        self.reportWriter.finished.connect(self.reportWriter.deleteLater)
        self.reportThread.finished.connect(self.reportThread.deleteLater)

        self.reportWriter.moveToThread(self.reportThread)

        self.reportWriter.progress.connect(self.updateProgress)

        self.reportThread.start()
        self.updateLog('Start to generate reports...')

        self.window.LipoAssay_runButton.setEnabled(False) # Block 'Run' button
        self.reportThread.finished.connect(
            lambda: self.window.LipoAssay_runButton.setEnabled(True) # Reset 'Run' button
            )
        self.reportThread.finished.connect(
            lambda: self.updateLog('Reports generated at: ' + self.project.path_result_main)
            )
        self.reportThread.finished.connect(
            lambda: self.restProgress()
            ) # Reset progress bar to rest
        try:
            self.reportThread.finished.connect(
                lambda: self._showLipoAssayResult()
                )
        except:
            print(sys.exc_info())


    def _showLipoAssayResult(self):
        df = pd.read_csv(self.project.path_result_main + '/Summary.csv')
        model = toolbox.PandasModel(df)
        self.window.LipoAssay_resultTable.setModel(model)


    # Super-resolution Anlaysis
    def _updateSRPreviousReconstructionAttempts(self):
        """
        This function updates the items in SupRes_previousReconstructionAttemptSelector, by listing all the directories parallel to the data path.
        """
        previous_reconstruction_attempts = [i for i in os.listdir(os.path.dirname(self.data_path)) if os.path.isdir(os.path.join(os.path.dirname(self.data_path), i))] # Find all previous reconstruction attempts and only keep folders
        previous_reconstruction_attempts.remove(os.path.basename(self.data_path)) # Remove original path from the list
        if len(previous_reconstruction_attempts) != 0:
            self.updateLog(str(len(previous_reconstruction_attempts)) + ' previous attempts are found.')
            self.previous_reconstruction_attempts = dict() # attempt name: attempt folder path
            # Clear the combo box and create items for each attempt
            self.window.SupRes_previousReconstructionAttemptSelector.clear()
            self.window.SupRes_previousReconstructionAttemptSelector.addItem("New")
            for i in previous_reconstruction_attempts:
                self.previous_reconstruction_attempts[i] = os.path.join(os.path.dirname(self.data_path), i).replace('\\', '/')
                self.window.SupRes_previousReconstructionAttemptSelector.addItem(i)
            self.window.SupRes_previousReconstructionAttemptSelector.setCurrentIndex(self.window.SupRes_previousReconstructionAttemptSelector.count() - 1) # Set the latest item as selection
        else:
            self.updateLog('No previous reconstruction attempt found for this data.')


    def clickLoadSRPreviousAttempts(self):
        # Check if data path exists
        data_path = self.window.SupRes_pathEntry.text()
        if os.path.isdir(data_path) == False:
            self.showMessage('w', 'Path to folder not found.')
            return 0
        else:
            self.data_path = data_path.replace('\\', '/')
            self.window.SupRes_pathEntry.setText(self.data_path)
            self.updateLog('Loading previous attempts from ' + self.data_path)

        if self.data_path.endswith('/'):
            self.data_path = self.data_path[:-1]

        self._updateSRPreviousReconstructionAttempts()


    def _updateSRPreviousCorrectionAttempts(self):
        """
        This function updates the items in SupRes_previousCorrectionAttemptsSelector, by listing all the directories present in the result path.
        """
        selected_attempt = self.window.SupRes_previousReconstructionAttemptSelector.currentText()
        previous_drift_attempts = [i for i in os.listdir(self.previous_reconstruction_attempts[selected_attempt]) if os.path.isdir(os.path.join(self.previous_reconstruction_attempts[selected_attempt], i))] # Only keep folders

        if len(previous_drift_attempts) != 0:
            self.window.SupRes_previousCorrectionAttemptsSelector.setEnabled(True)
            self.updateLog(str(len(previous_drift_attempts)) + ' previous drift correction attempts were found for this reconstruction attempt.')
            self.previous_drift_attempts = dict() # attempt name: attempt folder path
            # Clear the combo box and create items for each attempt
            self.window.SupRes_previousCorrectionAttemptsSelector.clear()
            for i in previous_drift_attempts:
                self.previous_drift_attempts[i] = os.path.join(os.path.join(os.path.dirname(self.data_path), selected_attempt), i).replace('\\', '/')
                self.window.SupRes_previousCorrectionAttemptsSelector.addItem(i)
            self.window.SupRes_previousCorrectionAttemptsSelector.setCurrentIndex(self.window.SupRes_previousCorrectionAttemptsSelector.count() - 1) # Set the latest item as selection
        else:
            pass


    def _SRPreviousReconstructionAttemptSelected(self):
        selected_attempt = self.window.SupRes_previousReconstructionAttemptSelector.currentText()

        # Check if the parameter log for the previous attempt is available
        try:
            with open(os.path.join(self.previous_reconstruction_attempts[selected_attempt], 'parameters.txt'), 'r') as js_file:
                self.SRparameters = json.load(js_file)
        except FileNotFoundError:
            self.showMessage('w', 'Parameter info for selected attempt not found. Default parameters used.')
            return 0
        except KeyError:
            self.window.SupRes_runFidCorrButton.setEnabled(False)
            self.window.SupRes_previousCorrectionAttemptsSelector.clear()
            self.window.SupRes_previousCorrectionAttemptsSelector.setEnabled(False)
            return 1


        ind = self.window.SupRes_methodSelector.findText(self.SRparameters['method'])
        if ind >= 0:
            self.window.SupRes_methodSelector.setCurrentIndex(ind)

        if self.SRparameters['method'] == 'ThunderSTORM':
            self.window.SupRes_QEEntry.setText(str(self.SRparameters['quantum_efficiency']))

        self.window.SupRes_PixelSizeEntry.setText(str(self.SRparameters['pixel_size']))
        self.window.SupRes_CamBiasEntry.setText(str(self.SRparameters['camera_bias']))
        self.window.SupRes_CamGainEntry.setText(str(self.SRparameters['camera_gain']))
        self.window.SupRes_ExpTimeEntry.setText(str(self.SRparameters['exposure_time']))
        self.window.SupRes_SRScaleEntry.setText(str(self.SRparameters['scale']))

        self.window.SupRes_runFidCorrButton.setEnabled(True)
        self._updateSRPreviousCorrectionAttempts()
        return 1


    def _SRPreviousCorrectionAttemptSelected(self):
        selected_attempt = self.window.SupRes_previousCorrectionAttemptsSelector.currentText()

        try:
            self.path_result_corrected = self.previous_drift_attempts[selected_attempt]
            print(self.path_result_corrected)
        except KeyError:
            del self.path_result_corrected
            pass
        
        if selected_attempt == 'raw':
            ind = self.window.SupRes_FidCorrMethodSelector.findText('')
            self.window.SupRes_FidCorrMethodSelector.setCurrentIndex(ind)
            return 1
        else:
            correction_info = selected_attempt.split('_')
            if correction_info[0] == 'ThunderSTORM':
                if correction_info[1] == 'CrossCorrelation':
                    ind = self.window.SupRes_FidCorrMethodSelector.findText('Cross-correlation - ThunderSTORM')
                    self.window.SupRes_FidCorrMethodSelector.setCurrentIndex(ind)
                    self.window.SupRes_FidCorrParaEntry1.setText(correction_info[2])
                    self.window.SupRes_FidCorrParaEntry2.setText(correction_info[3])
                    return 1
                elif correction_info[1] == 'FidMarker':
                    ind = self.window.SupRes_FidCorrMethodSelector.findText('Fiducial marker - ThunderSTORM')
                    self.window.SupRes_FidCorrMethodSelector.setCurrentIndex(ind)
                    self.window.SupRes_FidCorrParaEntry1.setText(correction_info[2])
                    self.window.SupRes_FidCorrParaEntry2.setText(correction_info[3])
                    return 1
                else:
                    pass # Space for other drift correction methods
            else:
                pass


    def _methodOptSR(self):
        """
        Block/Release parameter entry when a method is selected
        Change the options for fiducial correction for different reconstruction method
        """
        GDSC_fid_corr_methods = ['', 'Fiducial marker - ThunderSTORM', 'Cross-correlation - ThunderSTORM'] # The methods listed will be deleted when ThunderSTROM is selected ##'Auto fiducial
        ThunderSTORM_fid_corr_methods = ['', 'Fiducial marker - ThunderSTORM', 'Cross-correlation - ThunderSTORM']

        if self.window.SupRes_methodSelector.currentText() == 'GDSC SMLM 1':
            self.window.SupRes_QELabel.setEnabled(False)
            self.window.SupRes_QEEntry.setEnabled(False)
            self.window.SupRes_FidCorrMethodSelector.clear()
            for i in GDSC_fid_corr_methods:
                self.window.SupRes_FidCorrMethodSelector.addItem(i)

        elif self.window.SupRes_methodSelector.currentText() == 'ThunderSTORM':
            self.window.SupRes_QELabel.setEnabled(True)
            self.window.SupRes_QEEntry.setEnabled(True)
            self.window.SupRes_FidCorrMethodSelector.clear()
            for i in ThunderSTORM_fid_corr_methods:
                self.window.SupRes_FidCorrMethodSelector.addItem(i)


    def _methodOptSRFidCorr(self):
        """
        Change the parameter required for fiducial correction methods.
        """
        if self.window.SupRes_FidCorrMethodSelector.currentText() == '':
            self.window.SupRes_FidCorrParaLabel1.setEnabled(False)
            self.window.SupRes_FidCorrParaLabel2.setEnabled(False)
            self.window.SupRes_FidCorrParaEntry1.setEnabled(False)
            self.window.SupRes_FidCorrParaEntry2.setEnabled(False)
        else:
            self.window.SupRes_FidCorrParaLabel1.setEnabled(True)
            self.window.SupRes_FidCorrParaLabel2.setEnabled(True)
            self.window.SupRes_FidCorrParaEntry1.setEnabled(True)
            self.window.SupRes_FidCorrParaEntry2.setEnabled(True)

            if self.window.SupRes_FidCorrMethodSelector.currentText() == 'Auto fiducial':
                self.window.SupRes_FidCorrParaLabel1.setText('Brightness')
                self.window.SupRes_FidCorrParaLabel2.setText('Last Time/frames')
                self.window.SupRes_FidCorrParaEntry1.setText('10000')
                self.window.SupRes_FidCorrParaEntry2.setText('500')
            elif self.window.SupRes_FidCorrMethodSelector.currentText() == 'Fiducial marker - ThunderSTORM':
                self.window.SupRes_FidCorrParaLabel1.setText('Max distance/nm')
                self.window.SupRes_FidCorrParaLabel2.setText('Min visibility ratio')
                self.window.SupRes_FidCorrParaEntry1.setText('40.0')
                self.window.SupRes_FidCorrParaEntry2.setText('0.1')
            elif self.window.SupRes_FidCorrMethodSelector.currentText() == 'Cross-correlation - ThunderSTORM':
                self.window.SupRes_FidCorrParaLabel1.setText('Bin size')
                self.window.SupRes_FidCorrParaLabel2.setText('Magnification')
                self.window.SupRes_FidCorrParaEntry1.setText('10')
                self.window.SupRes_FidCorrParaEntry2.setText('5.0')


    def clickSRRun(self):
        guard = self._checkSRParameters()
        if guard == 1:
            guard = self._runSRReconstruction()


    def clickSRfidCorr(self):
        if  self.window.SupRes_FidCorrMethodSelector.currentText() == '':
            self.showMessage('w', 'No drift correction method was selected.')
        else:
            guard = self._checkSRParameters()
            if guard == 1:
                guard = self._runSRFidCorr()


    def _checkSRParameters(self):
        # Check if data path exists
        data_path = self.window.SupRes_pathEntry.text()
        if os.path.isdir(data_path) == False:
            self.showMessage('w', 'Path to folder not found.')
            return 0
        else:
            self.data_path = data_path.replace('\\', '/')
            self.window.SupRes_pathEntry.setText(self.data_path)
            self.updateLog('Data path set to ' + self.data_path)

        try: # Obtain methods and reconstruction parameters from UI
            self.SRparameters = {
            'method' : self.window.SupRes_methodSelector.currentText(),
            'pixel_size' : float(self.window.SupRes_PixelSizeEntry.text()),
            'camera_bias' : float(self.window.SupRes_CamBiasEntry.text()),
            'camera_gain' : float(self.window.SupRes_CamGainEntry.text()),
            'exposure_time' : float(self.window.SupRes_ExpTimeEntry.text()),
            'scale' : float(self.window.SupRes_SRScaleEntry.text()),
            'fid_method' : self.window.SupRes_FidCorrMethodSelector.currentText(),
            'signal_strength' : 40,
            'precision': 20.0,
            'min_photons': 0,
            'smoothing_factor': 0.25
            }
            if self.SRparameters['method'] == 'ThunderSTORM': # Quantum efficiency is solely required for ThunderSTORM
                self.SRparameters['quantum_efficiency'] = float(self.window.SupRes_QEEntry.text())

            # Obtain the corresponding parameters for the drift correction method selected
            if self.SRparameters['fid_method'] == 'Auto fiducial':
                self.SRparameters['fid_brightness'] = float(self.window.SupRes_FidCorrParaEntry1.text())
                self.SRparameters['fid_time'] = float(self.window.SupRes_FidCorrParaEntry2.text())
            elif self.SRparameters['fid_method'] == 'Fiducial marker - ThunderSTORM':
                self.SRparameters['max_distance'] = float(self.window.SupRes_FidCorrParaEntry1.text())
                self.SRparameters['min_visibility'] = float(self.window.SupRes_FidCorrParaEntry2.text())
            elif self.SRparameters['fid_method'] == 'Cross-correlation - ThunderSTORM':
                self.SRparameters['bin_size'] = int(self.window.SupRes_FidCorrParaEntry1.text())
                self.SRparameters['magnification'] = float(self.window.SupRes_FidCorrParaEntry2.text())
            else:
                pass

            if self.window.SupRes_TempGroupingCheck.isChecked(): # Obtain parameters for temporal grouping if the method is required
                self.SRparameters['temporal_grouping'] = {
                "dThresh": float(self.window.SupRes_dThreshEntry.text()), # in nm
                "min_loc": float(self.window.SupRes_minLocEntry.text()),
                "tThresh": float(self.window.SupRes_tThreshEntry.text()),
                "min_frame": float(self.window.SupRes_minFrameEntry.text()),
                "min_burst": float(self.window.SupRes_minBurstEntry.text()),
                "min_on_prop": float(self.window.SupRes_minOnPropEntry())
                }
            if self.window.SupRes_DBSCANCheck.isChecked():# Obtain parameters for DBSCAN if the method is required
                self.SRparameters['DBSCAN'] = {
                "eps": float(self.window.SupRes_EPSEntry.text()),
                "min_sample": float(self.window.SupRes_minSampleEntry.text())
                }

        except ValueError:
            self.showMessage('w', 'The parameters must be numbers.')
            return 0

        selected_attempt = self.window.SupRes_previousReconstructionAttemptSelector.currentText()
        if selected_attempt != "New":
            self.project = SuperResAnalysis(self.data_path, self.SRparameters) # Create project for super resolution analysis
            self.project.path_result_main = self.previous_reconstruction_attempts[selected_attempt]
            self.project.path_result_raw = self.project.path_result_main + '/raw'
            return 1
        else:
            self.project = SuperResAnalysis(self.data_path, self.SRparameters) # Create project for super resolution analysis
            if self.project.error != 1:
                self.showMessage('c', self.project.error)
                return 0
            else:
                return 1


    def _runSRReconstruction(self):
        self.initialiseProgress('Reconstructing SR images...', len(self.project.fov_paths))
        # Create a QThread object
        self.SRThread = QThread()
        # Create a worker object
        self.SRWorker = toolbox.SRWorker('Reconstruction', self.project, self.IJ)

        # Connect signals and slots
        self.SRThread.started.connect(self.SRWorker.run)
        self.SRWorker.finished.connect(self.SRThread.quit)
        self.SRWorker.finished.connect(self.SRWorker.deleteLater)
        self.SRThread.finished.connect(self.SRThread.deleteLater)
        # Move worker to the thread
        self.SRWorker.moveToThread(self.SRThread)
        # Connect progress signal to GUI
        self.SRWorker.progress.connect(self.updateProgress)
        # Start the thread
        self.SRThread.start()
        self.updateLog('Starting reconstruction...')
        
        # UI response
        self.window.SupRes_runReconstructionButton.setEnabled(False) # Block 'Run Reconstruction' button
        self.SRThread.finished.connect(
            lambda: self.window.SupRes_runReconstructionButton.setEnabled(True) # Reset 'Run Reconstruction' button
            )
        self.window.SupRes_loadButton.setEnabled(False) # Block 'Load' button
        self.SRThread.finished.connect(
            lambda: self.window.SupRes_loadButton.setEnabled(True) # Reset 'Load' button
            )
        self.window.SupRes_runFidCorrButton.setEnabled(False) # Block 'Run Fiducial Correction' button
        self.SRThread.finished.connect(
            lambda: self.window.SupRes_runFidCorrButton.setEnabled(True) # Enable 'Run fiducial correction' button
            )
        self.SRThread.finished.connect(
            lambda: self._updateSRPreviousReconstructionAttempts() # Refresh previous reconstruction attempt list
            )
        # Passing next job
        self.SRThread.finished.connect(
            lambda: self.updateLog('Reconstruction completed.')
            )
        self.SRThread.finished.connect(
            lambda: self.restProgress()
            ) # Reset progress bar to rest
        if self.SRparameters['fid_method'] == '': # if no fid method selected, skip. Otherwise trigger drift correction
            pass 
        else:
            try:
                self.SRThread.finished.connect(
                    lambda: self._runSRFidCorr()
                    ) 
            except:
                print(sys.exc_info())


    def _runSRFidCorr(self):
        self.initialiseProgress('Drift correcting...', len(self.project.fov_paths))
        # Create a QThread object
        self.SRThread = QThread()
        # Create a worker object
        self.SRWorker = toolbox.SRWorker('FiducialCorrection', self.project, self.IJ)

        # Connect signals and slots
        self.SRThread.started.connect(self.SRWorker.run)
        self.SRWorker.finished.connect(self.SRThread.quit)
        self.SRWorker.finished.connect(self.SRWorker.deleteLater)
        self.SRThread.finished.connect(self.SRThread.deleteLater)
        # Move worker to the thread
        self.SRWorker.moveToThread(self.SRThread)
        # Connect progress signal to GUI
        self.SRWorker.progress.connect(self.updateProgress)
        # Start the thread
        self.SRThread.start()
        self.updateLog('Starting drift correction by ' + self.SRparameters['fid_method'] + '...')
        
        # UI response
        self.window.SupRes_runReconstructionButton.setEnabled(False) # Block 'Run Reconstruction' button
        self.SRThread.finished.connect(
            lambda: self.window.SupRes_runReconstructionButton.setEnabled(True) # Reset 'Run Reconstruction' button
            )
        self.window.SupRes_loadButton.setEnabled(False) # Block 'Load' button
        self.SRThread.finished.connect(
            lambda: self.window.SupRes_loadButton.setEnabled(True) # Reset 'Load' button
            )
        self.window.SupRes_runFidCorrButton.setEnabled(False) # Block 'Run Fiducial Correction' button
        self.SRThread.finished.connect(
            lambda: self.window.SupRes_runFidCorrButton.setEnabled(True) # Reset 'Fiducial Correction' button
            )
        self.SRThread.finished.connect(
            lambda: self._updateSRPreviousCorrectionAttempts# Add work to attempt list
            )
        # Passing next job
        self.SRThread.finished.connect(
            lambda: self.updateLog('Drift correction completed.')
            )
        self.SRThread.finished.connect(
            lambda: self.restProgress()
            ) # Reset progress bar to rest
#        try:
#            self.SRThread.finished.connect(
#                lambda: self._generateDFLSPReports()
#                ) # Generate reports
#        except:
#            print(sys.exc_info())


    def _runClustering(self):
        pass


    # Help informations
    def helpComDet(self):
        self.showMessage('i', r"""                                                      ComDet
Parameters:
    Threshold: signal to noise ratio
    Size: estimated size of particles (can be larger than the estimation)

My (Ron's) way of using this method is to detect all the spots in images, regardless they are background noise or actual particles. Then use the orthogonal analysis to set a threshold on intensity per area to remove the noise. Hence I would use a very low threshold for particle detection - normally 3SD.

Please see https://github.com/ekatrukha/ComDet/wiki/How-does-detection-work%3F for details in how the detection works.
            """)


    def helpTrevor(self):
        self.showMessage('i', r"""                                                      Trevor
Parameters:
    Threshold: Pick out pixels with intensities over (μ+threshold*σ). Recommended value of threshold is 1. Higher value results in fewer dots.
    Size: Size of erosion disk. The size has to be an integer. Recommended value is 2. Higher value results in fewer dots.
Image processing procedure:
    1. Top-hat filtering the image.
    2. Convolute the image with an Mexican hat filter, resulting in negative values around the aggregates.
    3. Remove dots with intensities lower than (μ+threshold*σ).
    4. Erode and dilate the image to remove small noisy dots.
    5. Label the aggregates, output area, integrated intensity values, etc.
            """)


    def helpFrozen(self):
        self.showMessage('i', r"""
If you encountered program freezing with the progress bar reached 100%, please restart the program and re-run the step you got stuck with (from the Tools command list).
Please contact Ron Xia (zx252@cam.ac.uk) if you keep having this problem. This is a known bug in the program which should be fixed in later releases. Thanks for your understanding.
            """)


# Supporting widgets
class TagDataPopup(QWidget):
    finished = Signal()
    def __init__(self, parent=None):
        self.parent = parent
        try:
            self.mainWindow = self.parent.window
        except AttributeError:
            self.mainWindow = None

        super(TagDataPopup, self).__init__(parent=self.mainWindow)
        self.loadUI()
        

    def loadUI(self):

        path = os.path.join(os.path.dirname(__file__), "UI_form/TagDataPopup.ui")
        ui_file = QFile(path)
        if not ui_file.open(QIODevice.ReadOnly):
            print(f"Cannot open {ui_file_name}: {ui_file.errorString()}")
            sys.exit(-1)

        loader = QUiLoader()
        self.window = loader.load(ui_file, self.mainWindow)

        self.window.loadButton.clicked.connect(self.clickLoadButton)
        self.window.buttonBox.button(self.window.buttonBox.Apply).clicked.connect(self._applyTags)

        ui_file.close()
        if not self.window:
            print(loader.errorString())
            sys.exit(-1)
        
        df = pd.read_csv(os.path.join(os.path.dirname(__file__), "UI_form/data_tagging_sample.csv"))
        model = toolbox.PandasModel(df)
        self.window.exampleTableView.setModel(model)


    def clickLoadButton(self):
        self.path_tags = QFileDialog.getOpenFileName(parent=self.window, caption='Select tags source', dir=self.parent.project.path_data_main, filter="Text files (*.csv)")
        try:
            self.path_tags = list(self.path_tags)[0]
            self.window.pathLabel.setText(self.path_tags)
            df = pd.read_csv(self.path_tags)
            model = toolbox.PandasModel(df)
            self.window.tagsTableView.setModel(model)
        except FileNotFoundError:
            pass


    def _applyTags(self):
        fileToUpdate = ['Summary.csv', 'QC.csv']
        tag_df = pd.read_csv(self.path_tags)
        for file in fileToUpdate:
            data_df = pd.read_csv(os.path.join(self.parent.project.path_result_main, file))
            cols_to_use = ['Well'] + list(tag_df.columns.difference(data_df.columns))
            updated_df = pd.merge(data_df, tag_df[cols_to_use], on='Well')
            updated_df.to_csv(os.path.join(self.parent.project.path_result_main, file), index=False)
        self.finished.emit()



class GroupingPopup(QWidget):
    output = Signal(str, str)
    finished = Signal()
    def __init__(self, parent=None):
        self.parent = parent
        try:
            self.mainWindow = self.parent.window
        except AttributeError:
            self.mainWindow = None
        super(GroupingPopup, self).__init__(parent=self.mainWindow)
        self.loadUI()


    def loadUI(self):

        path = os.path.join(os.path.dirname(__file__), "UI_form/GroupingPopup.ui")
        ui_file = QFile(path)
        if not ui_file.open(QIODevice.ReadOnly):
            print(f"Cannot open {ui_file_name}: {ui_file.errorString()}")
            sys.exit(-1)

        loader = QUiLoader()

        self.window = loader.load(ui_file, self.mainWindow)
        self.window.buttonBox.button(self.window.buttonBox.Apply).clicked.connect(self.clickedApply)

        rm_list = ['NoOfFoV', 'ParticlePerFoV', 'MeanSize', 'MeanIntegrInt', 'MeanIntPerArea']
        df = pd.read_csv(self.parent.project.path_result_main + '/Summary.csv')
        self.options = list(df.columns.difference(rm_list)) + ['None']

        self.window.experimentBoxLayout = QVBoxLayout(self.window.experimentBox)
        self.window.experimentButtonGroup = QButtonGroup()
        # list of column names remove from the grouping option
        for c, i in enumerate(self.options):
            if i != 'Well':
                self.window.radioButton = QRadioButton(i)
                self.window.experimentBoxLayout.addWidget(self.window.radioButton)
                self.window.experimentButtonGroup.addButton(self.window.radioButton, id=c)
            if i == 'None':
                self.window.radioButton.setChecked(True)

        self.window.xaxisBoxLayout = QVBoxLayout(self.window.xaxisBox)
        self.window.xaxisButtonGroup = QButtonGroup()
        # list of column names remove from the grouping option
        for c, i in enumerate(self.options):
            if i != 'None':
                self.window.radioButton = QRadioButton(i)
                self.window.xaxisBoxLayout.addWidget(self.window.radioButton)
                self.window.xaxisButtonGroup.addButton(self.window.radioButton, id=c)
            if i == 'Well':
                self.window.radioButton.setChecked(True)

        ui_file.close()
        if not self.window:
            print(loader.errorString())
            sys.exit(-1)


    def clickedApply(self):
        experimentSelection = self.window.experimentButtonGroup.checkedId()
        xaxisSelection = self.window.xaxisButtonGroup.checkedId()
        if experimentSelection == xaxisSelection:
            msgBox = QMessageBox(self.mainWindow)
            msgBox.setIcon(QMessageBox.Warning)
            msgBox.setWindowTitle('Warning')
            msgBox.setText('Cannot select the same condition.')
            returnValue = msgBox.exec_()
        else:
            self.output.emit(self.options[experimentSelection], self.options[xaxisSelection])
            self.finished.emit()



class OrthogonalAnalysisPopup(QWidget):
    finished = Signal()
    def __init__(self, task, df, xaxis, parent=None):
        self.parent = parent
        self.task = str(task)
        self.org_df = df
        self.xaxis = xaxis
        self.thresholded_df = self.org_df

        try:
            self.mainWindow = self.parent.window
        except AttributeError:
            self.mainWindow = None
        super(OrthogonalAnalysisPopup, self).__init__(parent=self.mainWindow)
        self.loadUI()
        

    def loadUI(self):

        path = os.path.join(os.path.dirname(__file__), "UI_form/OrthogonalAnalysisPopup.ui")
        ui_file = QFile(path)
        if not ui_file.open(QIODevice.ReadOnly):
            print(f"Cannot open {ui_file_name}: {ui_file.errorString()}")
            sys.exit(-1)

        class UiLoader(QUiLoader): # Enable promotion to custom widgets
            def createWidget(self, className, parent=None, name=""):
                if className == "PlotWidget":
                    return pg.PlotWidget(parent=parent) # promote to pyqtgraph.PlotWidget
                return super().createWidget(className, parent, name)

        loader = UiLoader()

        self.window = loader.load(ui_file, self.mainWindow)
        self.window.setWindowTitle('Orthogonal Analysis - ' + self.task)

        self.window.oa_applyButton.clicked.connect(self.applyThresholds)
        self.window.oa_defaultButton.clicked.connect(self.resetDefault)
        self.window.oa_saveResultButton.clicked.connect(self.saveData)
        self.window.oa_cancelButton.clicked.connect(self.cancel)
        self.window.oa_plotSelector.currentIndexChanged.connect(self.applyThresholds)

        self._updateParticlePlot(self.org_df)
        self._plotIntnArea()

        ui_file.close()
        if not self.window:
            print(loader.errorString())
            sys.exit(-1)


    def _updateParticlePlot(self, df):
        self.window.oa_particlePlot.clear()
        # Particle plot
        rm_list = ['FoV', 'NArea', 'IntegratedInt', 'IntPerArea']
        keep_list = list(df.columns.difference(rm_list)) # get list of conditions
        sum_df = df.groupby(keep_list+ ['FoV']).size()
        sum_df = sum_df.reset_index(drop=False)
        sum_df = sum_df.groupby(keep_list).mean()
        sum_df = sum_df.reset_index(drop=False)
        sum_df = sum_df.rename(columns={0: "ParticlePerFoV"})
        
        ### Set string axis # use well if no x-axis selected
        self.xdict = dict(enumerate(sum_df[self.xaxis]))
        self.stringaxis = pg.AxisItem(orientation='bottom')
        self.stringaxis.setTicks([self.xdict.items()])
        self.window.oa_particlePlot.setAxisItems(axisItems = {'bottom': self.stringaxis})
        self.window.oa_particlePlot.showGrid(y=True)
        self.window.oa_particlePlot.setMouseEnabled(y=False)
        self.window.oa_particlePlot.setLabel('left', 'Particle per FoV')
        self.window.oa_particlePlot.setLabel('bottom', self.xaxis)
        self.window.oa_particlePlot.setRange(xRange=[0, np.max(list(self.xdict.keys()))])

        if self.window.oa_plotSelector.currentText() == "Bar plot":
            bargraph = pg.BarGraphItem(x=list(self.xdict.keys()), height=sum_df.ParticlePerFoV, width=0.6)
            self.window.oa_particlePlot.addItem(bargraph)
        else:
            self.window.oa_particlePlot.plot(x=list(self.xdict.keys()), y=sum_df.ParticlePerFoV, pen=(0,0,0,255))


    def _plotIntnArea(self):

        def plotHist(widget, fig_type, condition, color):
            color = list(pg.colorTuple(pg.intColor(color)))
            color[3] = 100
            color = tuple(color)

            df = self.org_df.loc[self.org_df[self.xaxis] == condition]
            y, x = np.histogram(df[fig_type], bins=np.linspace(0, df[fig_type].max(), 100)) #* change bin size?
            bg = pg.BarGraphItem(x=x[:len(y)], name=condition, height=y, width=(x[1]-x[0]), brush=color)
            widget.addItem(bg)


        # IntPerArea plot
        self.window.oa_intperareaPlot.addLegend()
        self.window.oa_intperareaPlot.setMouseEnabled(y=False)
        self.window.oa_intperareaPlot.setLabel('left', 'Count')
        self.window.oa_intperareaPlot.setLabel('bottom', 'Intensity per Area')

        self.window.oa_intperareaPlotLine = pg.InfiniteLine(angle=90, movable=True, pen='r')
        self.window.oa_intperareaPlot.addItem(self.window.oa_intperareaPlotLine, ignoreBounds=True)

        for c, i in enumerate(self.org_df[self.xaxis].unique()):
            plotHist(self.window.oa_intperareaPlot, 'IntPerArea', i, c)
        

        # NArea plot
        self.window.oa_nareaPlot.addLegend()
        self.window.oa_nareaPlot.setMouseEnabled(y=False)
        self.window.oa_nareaPlot.setLabel('left', 'Count')
        self.window.oa_nareaPlot.setLabel('bottom', 'Size', units='pixels')

        self.window.oa_nareaPlotLine = pg.InfiniteLine(angle=90, movable=True, pen='r')
        self.window.oa_nareaPlot.addItem(self.window.oa_nareaPlotLine, ignoreBounds=True)

        for c, i in enumerate(self.org_df[self.xaxis].unique()):
            plotHist(self.window.oa_nareaPlot, 'NArea', i, c)
        

    def applyThresholds(self):
        self.thresholded_df = self.org_df.loc[self.org_df.IntPerArea >= self.window.oa_intperareaPlotLine.value()]
        self.thresholded_df = self.thresholded_df.loc[self.thresholded_df.NArea >= self.window.oa_nareaPlotLine.value()]

        self._updateParticlePlot(self.thresholded_df)


    def resetDefault(self):
        self.thresholded_df = self.org_df
        self._updateParticlePlot(self.org_df)


    def saveData(self):
        self.applyThresholds()

        thred_path = self.parent.project.path_result_main + '/Thred_results'
        if os.path.isdir(thred_path) != True:
            os.mkdir(thred_path)
        rm_list = ['FoV', 'NArea', 'IntegratedInt', 'IntPerArea']
        keep_list = list(self.thresholded_df.columns.difference(rm_list)) # get list of conditions
        output_df = self.thresholded_df.groupby(keep_list+ ['FoV']).size()
        output_df = output_df.reset_index(drop=False)
        output_df = output_df.groupby(keep_list).mean()
        output_df = output_df.reset_index(drop=False)
        output_df = output_df.rename(columns={0: "ParticlePerFoV"})

        output_df['thred_IntPerArea'] = self.window.oa_intperareaPlotLine.value()
        output_df['thred_NArea'] = self.window.oa_nareaPlotLine.value()
        output_df.to_csv(thred_path + '/' + self.task  + '.csv')
        self.parent.updateLog('Thresholded result saved as ' + thred_path + '/' + self.task  + '.csv.')
        try:
            self.finished.emit()
        except:
            print(sys.exc_info())


    def cancel(self):
        self.finished.emit()



if __name__ == "__main__":

    app = QApplication([])
    app.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), "UI_form/lulu.ico")))
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())
