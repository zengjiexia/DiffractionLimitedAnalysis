import sys
import os

import PySide6
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QMessageBox, QProgressDialog, QFileDialog, QVBoxLayout, QRadioButton, QButtonGroup
from PySide6.QtCore import QFile, QIODevice, Slot, Qt, QThread, Signal, QRect
from PySide6.QtUiTools import QUiLoader
import pyqtgraph as pg
import toolbox
from logics import SimPullAnalysis
import pandas as pd
pg.setConfigOption('background', 'w')

class DiffractionLimitedAnalysis_UI(QMainWindow):

    def __init__(self):
        super(DiffractionLimitedAnalysis_UI, self).__init__()
        self.loadUI()


    def loadUI(self):

        path = os.path.join(os.path.dirname(__file__), "UI_form/DiffractionLimitedAnalysis.ui")
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

        # main window widgets
        self.window.main_runButton.clicked.connect(self.clickMainWindowRun)
        self.window.main_tagButton.clicked.connect(self.clickMainWindowTag)
        self.window.main_oaButton.clicked.connect(self.clickMainWindowOA)

        ui_file.close()
        if not self.window:
            print(loader.errorString())
            sys.exit(-1)
        self.window.show()
        sys.exit(app.exec_())       


    def updateLog(self, message):
        self.window.main_logBar.insertPlainText(message + '\n')
        self.window.main_logBar.verticalScrollBar().setValue(
            self.window.main_logBar.verticalScrollBar().maximum())
        # auto scroll down to the newest message


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
        msgBox.setText(message)
        returnValue = msgBox.exec_()


    def clickMainWindowRun(self):
        guard = self._checkParameters()
        if guard == 1:
            #guard = self._runAnalysis()
            guard = self._generateReports() # testing solely report generation
            #guard = self._showResult_main() # testing solely result presentation
        else:
            self.showMessage('w', 'Failed to locate particles using ComDet. Please see help.')


    def _checkParameters(self):
        #Check if data path exists
        data_path = self.window.main_pathEntry.text()
        if os.path.isdir(data_path) == False:
            self.showMessage('w', 'Error: Path to folder not found.')
            return 0
        else:
            self.data_path = data_path
            self.window.main_pathEntry.setText(self.data_path)
            self.updateLog('Data path set to '+data_path)

        #Check input: threshold
        try:
            self.threshold = int(self.window.main_thresholdEntry.text())
            self.window.main_thresholdEntry.setText(str(self.threshold))
        except ValueError:
            self.showMessage('c', 'Please input a number for threshold.')
            return 0
        if self.threshold <= 2 or self.threshold >= 20:
            self.updateLog('Threshold set as '+str(self.threshold)+' SD. Suggested range would be 3-20 SD.')
        else:
            self.updateLog('Threshold set at '+str(self.threshold)+' SD.')

        #Check input: estimated size
        try:
            self.size = int(self.window.main_sizeEntry.text())
            self.window.main_sizeEntry.setText(str(self.size))
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


    def _runAnalysis(self):
        self.initialiseProgress('Locating particles...', len(self.project.fov_paths))

        # Create a QThread object
        self.PFThread = QThread()
        # Create a worker object
        self.particleFinder = toolbox.ParticleFinder('ComDet', self.project, self.size, self.threshold) #* method selection

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
        self.window.main_runButton.setEnabled(False) # Block 'Run' button
        self.PFThread.finished.connect(
            lambda: self.window.main_runButton.setEnabled(True) # Reset 'Run' button
            )
        self.PFThread.finished.connect(
            lambda: self.updateLog('Particles in images are located.')
            )
        self.PFThread.finished.connect(
            lambda: self.restProgress()
            ) # Reset progress bar to rest

        try:
            self.PFThread.finished.connect(
                lambda: self._generateReports()
                ) # Generate reports
        except:
            print(sys.exc_info())


    def _generateReports(self):
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

        self.window.main_runButton.setEnabled(False) # Block 'Run' button
        self.reportThread.finished.connect(
            lambda: self.window.main_runButton.setEnabled(True) # Reset 'Run' button
            )
        self.reportThread.finished.connect(
            lambda: self.window.main_tagButton.setEnabled(True)
            )
        self.reportThread.finished.connect(
            lambda: self.updateLog('Reports generated at: ' + self.project.path_result_main)
            )
        self.reportThread.finished.connect(
            lambda: self.restProgress()
            ) # Reset progress bar to rest

        try:
            self.reportThread.finished.connect(
                lambda: self._showResult_main()
                )
        except:
            print(sys.exc_info())


    def _showResult_main(self):
        df = pd.read_csv(self.project.path_result_main + '/Summary.csv')
        model = toolbox.PandasModel(df)
        self.window.main_resultTable.setModel(model)


    def clickMainWindowTag(self):
        self.tagdatapopup = TagDataPopup(parent=self)
        self.tagdatapopup.window.show()
        self.tagdatapopup.finished.connect(
            lambda: self._showResult_main()
            )
        self.tagdatapopup.finished.connect(self.tagdatapopup.window.close)
        self.tagdatapopup.finished.connect(
            lambda: self.updateLog('Tagged data saved at: ' + self.project.path_result_main)
            )
        self.tagdatapopup.finished.connect(
            lambda: self.window.main_oaButton.setEnabled(True)
            )
        


    def clickMainWindowOA(self):
        self.groupingpopup = GroupingPopup(parent=self)
        self.groupingpopup.window.show()
        self.groupingpopup.output.connect(self._oaProcess)
        self.groupingpopup.finished.connect(self.groupingpopup.window.close)


    def _oaProcess(self, experimentSelection, xaxisSelection):
        df = pd.read_csv(self.project.path_result_main + '/QC.csv')
        if experimentSelection == 'None':
            self.oapopup = OrthogonalAnalysisPopup(df=df, xaxis=xaxisSelection, parent=self)
            self.oapopup.window.show()
        else:
            tasks = list(df[experimentSelection].unique())
            for t in tasks:
                t_df = df.loc[df[experimentSelection] == t]
                self.oapopup = OrthogonalAnalysisPopup(df=t_df, xaxis=xaxisSelection, parent=self)
                self.oapopup.window.show()
            #* wait for one session to finish before start another



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
        self.path_tags = QFileDialog.getOpenFileName(parent=self.window, caption='Select tags source', dir=os.path.dirname(__file__), filter="Text files (*.csv)")
        self.path_tags = list(self.path_tags)[0]
        self.window.pathLabel.setText(self.path_tags)
        df = pd.read_csv(self.path_tags)
        model = toolbox.PandasModel(df)
        self.window.tagsTableView.setModel(model)


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
    def __init__(self, df, xaxis, parent=None):
        self.parent = parent
        self.org_df = df
        self.xaxis = xaxis

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
        self.window.oa_applyButton.clicked.connect(self.function1)
        self._updatePlots(self.org_df)

        ui_file.close()
        if not self.window:
            print(loader.errorString())
            sys.exit(-1)


    def _updatePlots(self, df):
        # Particle plot
        rm_list = ['FoV', 'NArea', 'IntegratedInt', 'IntPerArea']
        keep_list = list(df.columns.difference(rm_list)) # get list of conditions
        sum_df = df.groupby(keep_list+ ['FoV']).size()
        sum_df = sum_df.reset_index(drop=False)
        sum_df = sum_df.groupby(keep_list).mean()
        sum_df = sum_df.reset_index(drop=False)
        sum_df = sum_df.rename(columns={0: "ParticlePerFoV"})
        
        ### Set string axis # use well if no x-axis selected
        xdict = dict(enumerate(sum_df[self.xaxis]))
        stringaxis = pg.AxisItem(orientation='bottom')
        stringaxis.setTicks([xdict.items()])
        self.window.oa_particlePlot.setAxisItems(axisItems = {'bottom': stringaxis}) 

        particle_plot = self.window.oa_particlePlot.plot()
        particle_plot.setPen((200,200,100))
        particle_plot.setData(x=list(xdict.keys()), y=sum_df.ParticlePerFoV)

        # IntPerArea plot

        # NArea plot
    def function1(self):
        print('1111')



if __name__ == "__main__":

    app = QApplication([])
    widget = DiffractionLimitedAnalysis_UI()
    widget.show()
    sys.exit(app.exec_())
