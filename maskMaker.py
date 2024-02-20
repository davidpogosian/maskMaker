import os
import cv2
import time
import pickle
import pydicom
import threading
import numpy as np
import pandas as pd
import tkinter as tk
from dataset import *
from PIL import ImageTk, Image
from SAMInterface import SAMInterface
from tkinter import filedialog, simpledialog, ttk



class GlobalData:
    def __init__(self):
        self.currentDataset = Dataset()
        self.SAM = SAMInterface()
        self.currentDatasetName = "DefaultName"
        self.dataPath = "MRI_Data"
        self.annotationPath = "Radiologists Report.xlsx"

        self.currentImagePath = ""
        self.currentImage = None
        self.currentMask = None
        self.herniated = False

        self.patientDetails = ""
        self.selectionBox = None

        self.autoSave = False
        self.autoLoad = False
        self.imageLoaded = False

        self.autoSaveThread = None

globalData = GlobalData()



def getPatientIdFromPath(path):
    return int(path.split("/")[1])

def printArrayDetails(arr):
    print(f"shape: {arr.shape} \ndatatype: {arr.dtype} \nmin: {np.min(arr)} \nmax: {np.max(arr)}")

def imaToNdarray(path):
    arr = pydicom.dcmread(path).pixel_array
    return arr

def getVisualBinaryMask(mask, color_true=(0, 255, 0), color_false=(0, 0, 0), transparency=128):
    """
    Visualize a binary mask with transparency.

    Parameters:
        mask (numpy.ndarray): Binary mask array containing 0s and 1s.
        color_true (tuple): Color for true (1) values, default is green.
        color_false (tuple): Color for false (0) values, default is black.
        transparency (int): Transparency level for the mask, ranging from 0 (fully transparent) to 255 (fully opaque).
    
    Returns:
        numpy.ndarray: Visualized mask with colors and transparency.
    """
    # Create an empty array with the same shape as the mask, but with 4 channels for RGBA
    visualized_mask = np.zeros(mask.shape + (4,), dtype=np.uint8)

    # Set color for true values (1s) with transparency
    visualized_mask[mask == 1] = (*color_true, transparency)

    # Set color for false values (0s) with transparency
    visualized_mask[mask == 0] = (*color_false, 0)

    return visualized_mask

def alert(messag):
    alertWindow = tk.Toplevel()
    alertWindow.title("Alert")
    alertWindow.geometry("550x200")
    label = tk.Label(alertWindow, text=messag)
    label.pack(padx=10, pady=10)
    closeButton = tk.Button(alertWindow, text="Don't care", command=alertWindow.destroy)
    closeButton.pack(pady=5)

    # Close the window after 5 seconds
    alertWindow.after(5000, alertWindow.destroy)

def notification(messag, duration=1500):
    notificationWindow = tk.Toplevel()
    notificationWindow.geometry("200x100")
    notificationWindow.title("Mask Maker")

    label = tk.Label(notificationWindow, text=messag)
    label.pack(pady=10)

    notificationWindow.after(duration, notificationWindow.destroy)



class ImageCanvas(tk.Canvas):
    def __init__(self, tkParent):
        super().__init__(tkParent, bg="black")

    def resizeCanvas(self, width, height):
        self.config(width=width, height=height)

    def display(self, arr):
        image = Image.fromarray(arr)
        self.myImg = ImageTk.PhotoImage(image)
        self.resizeCanvas(self.myImg.width(), self.myImg.height())
        self.create_image(0, 0, anchor=tk.NW, image=self.myImg)

    def displayTwo(self, arr1, arr2):
        self.image1 = ImageTk.PhotoImage(Image.fromarray(arr1))
        self.image2 = ImageTk.PhotoImage(Image.fromarray(arr2))

        self.resizeCanvas(self.image1.width(), self.image1.height())

        self.imageObject1 = self.create_image(0, 0, anchor=tk.NW, image=self.image1)
        self.imageObject2 = self.create_image(0, 0, anchor=tk.NW, image=self.image2)

    def clear(self):
        self.delete("all")



class InputImageCanvas(ImageCanvas):
    def __init__(self, tkParent):
        super().__init__(tkParent)

        self.startX = None
        self.startY = None
        self.box = None

        self.bind("<Button-1>", self.onMouseClick)
        self.bind("<B1-Motion>", self.onMouseDrag)
        self.bind("<ButtonRelease-1>", self.onMouseRelease)

    def onMouseClick(self, event):
        self.startX = event.x
        self.startY = event.y
    
    def onMouseDrag(self, event):
        if self.box:
            self.delete(self.box)
        self.box = self.create_rectangle(self.startX, self.startY, event.x, event.y, outline="red")
    
    def onMouseRelease(self, event):
        globalData.selectionBox = [self.startX, self.startY, event.x, event.y]
        self.startX = None
        self.startY = None

    

class ImageFrame(ttk.Frame):
    def __init__(self, tkParent):
        super().__init__(tkParent)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Probably want to save this as well.
        self.currentImageLabel = InputImageCanvas(self)
        self.currentImageLabel.grid(row=0, column=0)
        
        self.maskImageLabel = ImageCanvas(self)
        self.maskImageLabel.grid(row=0, column=1)



class TreeviewFrame(ttk.Frame):
    def __init__(self, tkParent):
        super().__init__(tkParent)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        self.mainPanedWindow = tkParent # Sus.

        # Create a Scrollbar
        scrollbar = ttk.Scrollbar(self, orient="vertical")

        # Create a Treeview widget
        self.tree = ttk.Treeview(self, yscrollcommand=scrollbar.set)
        self.buildTreeview(globalData.dataPath)
        self.tree.tag_configure('ttk', background='yellow')
        self.tree.tag_bind('ttk', '<1>', lambda event: self.handleTreeItemClick(event)) 
        self.tree.grid(row=0, column=0, sticky="nsew")

        # Link the Treeview to the Scrollbar
        scrollbar.config(command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")

    def buildTreeview(self, path):
        for patient in os.listdir(path):
            patientPath = path + "/" + patient
            patiendNodeId = self.tree.insert('', 'end', text=patient)
            for session in os.listdir(patientPath):
                sessionPath = patientPath + "/" + session
                sessionNodeID = self.tree.insert(patiendNodeId, 'end', text=session)
                for scanType in os.listdir(sessionPath):
                    scanTypePath = sessionPath + "/" + scanType
                    scanTypeNodeId = self.tree.insert(sessionNodeID, 'end', text=scanType)
                    for scan in os.listdir(scanTypePath):
                        self.tree.insert(scanTypeNodeId, 'end', text=scan, tags=('ttk', 'simple'))

    def handleTreeItemClick(self, event):
        # Firstly, reset some stuff.
        globalData.currentMask = None
        globalData.imageLoaded = False
        globalData.selectionBox = None
        
        itemId = self.tree.identify_row(event.y)
        imagePath = self.tree.item(itemId, "text")
        parentId = self.tree.parent(itemId)

        while parentId != "":
            imagePath = self.tree.item(parentId, "text") + "/" + imagePath
            parentId = self.tree.parent(parentId)

        globalData.currentImagePath = globalData.dataPath + "/" + imagePath
        globalData.currentImage = imaToNdarray(globalData.currentImagePath)

        currentImageLabel = self.mainPanedWindow.imageFrameAndConsolePanedWindow.imageFrame.currentImageLabel
        maskImageLabel = self.mainPanedWindow.imageFrameAndConsolePanedWindow.imageFrame.maskImageLabel
        currentImageLabel.clear()
        maskImageLabel.clear()
        
        # Display current image.
        currentImageLabel.display(globalData.currentImage)

        # Alert the console.
        self.mainPanedWindow.imageFrameAndConsolePanedWindow.console.showPatientDetails(int(globalData.currentImagePath.split("/")[1]))

        if (globalData.autoLoad):
            self.mainPanedWindow.inputFrameAndDatasetTreeviewFramePanedWindow.handleLoadImageIntoSAM()




class DatasetTreeviewFrame(ttk.Frame):
    def __init__(self, tkParent):
        super().__init__(tkParent)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=12)
        self.grid_columnconfigure(0, weight=1)
        
        self.InputFrameAndDatasetTreeviewFramePanedWindow = tkParent # Sus.

        # Dataset name label.
        self.datasetNameLabel = tk.Label(self, text=globalData.currentDatasetName)
        self.datasetNameLabel.grid(row=0, column=0, sticky="n")

        # Create a Scrollbar.
        scrollbar = ttk.Scrollbar(self, orient="vertical")

        # Create a Treeview widget.
        self.tree = ttk.Treeview(self, yscrollcommand=scrollbar.set)
        self.tree.tag_bind("datum", '<1>', lambda event: self.handleTreeItemClick(event)) 
        self.tree.bind("<Delete>", self.deleteSelectedItems)
        self.tree.grid(row=1, column=0, sticky="nsew")

        # Link the Treeview to the Scrollbar.
        scrollbar.config(command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")

    def display(self):
        self.datasetNameLabel.config(text=globalData.currentDatasetName) 
        self.tree.delete(*self.tree.get_children())
        for i in range(len(globalData.currentDataset.data)):
            datum = globalData.currentDataset.data[i]
            patientId = getPatientIdFromPath(datum.imagePath)
            _, filename = os.path.split(datum.imagePath)
            datumText = f"{i}.{patientId}.{filename}.{datum.herniated}"
            self.tree.insert("", 'end', text=datumText, tags=("datum"), values=(i,))

    def deleteSelectedItems(self, event=None):
        selectedItems = self.tree.selection()
        # Delete ids (largest to smallest).
        idsToDelete = []
        for id in selectedItems:
            idsToDelete.append(int(self.tree.item(id, "values")[0]))
        idsToDelete.sort(reverse=True)
        for id in idsToDelete:
            globalData.currentDataset.data.pop(id)
        self.display() # Totally reload the treeview to avoid indexing issues.

    def handleTreeItemClick(self, event):
        globalData.currentImage = None
        globalData.currentMask = None
        globalData.imageLoaded = False
        globalData.selectionBox = None

        itemId = self.tree.identify_row(event.y)
        datum = globalData.currentDataset.data[int(self.tree.item(itemId, "values")[0])]

        currentImageLabel = self.InputFrameAndDatasetTreeviewFramePanedWindow.mainPanedWindow.imageFrameAndConsolePanedWindow.imageFrame.currentImageLabel
        maskImageLabel = self.InputFrameAndDatasetTreeviewFramePanedWindow.mainPanedWindow.imageFrameAndConsolePanedWindow.imageFrame.maskImageLabel
        currentImageLabel.clear()
        maskImageLabel.clear()
        
        # Display image.
        currentImageLabel.display(datum.image)

        # Display mask.
        maskImageLabel.displayTwo(datum.image, getVisualBinaryMask(datum.mask))

        # Alert the console.
        self.InputFrameAndDatasetTreeviewFramePanedWindow.mainPanedWindow.imageFrameAndConsolePanedWindow.console.display(datum.imagePath)



class Console(tk.Label):
    def __init__(self, tkParent):
        super().__init__(tkParent)
        self.df = pd.read_excel(globalData.annotationPath)

        self.text = "Patient information is displayed here"
        self.config(text=self.text)

        self.bind("<Configure>", self.updateWraplength)

    def display(self, text):
        self.text = text
        self.config(text=self.text)

    def showPatientDetails(self, patientNumber):
        globalData.patientDetails = self.getPatientDetails(patientNumber)
        self.display(globalData.patientDetails)

    def getPatientDetails(self, patientNumber):
        return f"{self.df.iloc[patientNumber - 1].iloc[0]}: {self.df.iloc[patientNumber - 1].iloc[1]}"
    
    def updateWraplength(self, event):
        self.config(wraplength=self.winfo_width() - 10)

    

class ImageFrameAndConsolePanedWindow(tk.PanedWindow):
    def __init__(self, tkParent):
        super().__init__(tkParent, orient="vertical", sashwidth=5, sashrelief=tk.RAISED)

        self.imageFrame = ImageFrame(self)
        self.add(self.imageFrame)

        self.console = Console(self)
        self.add(self.console)

        # Set initial sizes for the panes
        self.paneconfig(self.imageFrame, minsize=100)
        self.paneconfig(self.console, minsize=40)
        


class InputFrameAndDatasetTreeviewFramePanedWindow(tk.PanedWindow):
    def __init__(self, tkParent):
        super().__init__(tkParent, orient="vertical", sashwidth=5, sashrelief=tk.RAISED)

        self.mainPanedWindow = tkParent # Sus.

        # Input frame.
        self.inputFrame = ttk.Frame(self, borderwidth=2, relief="groove")
        self.add(self.inputFrame)

        # Buttons.
        loadImageIntoSAMButton = tk.Button(self.inputFrame, text="Load Image into SAM", command=self.handleLoadImageIntoSAM)
        loadImageIntoSAMButton.grid(row=0, column=0)

        makeMaskButton = tk.Button(self.inputFrame, text="M<A>ke Mask", command=self.handleMakeMask)
        makeMaskButton.grid(row=1, column=0)

        saveImageAndMaskButton = tk.Button(self.inputFrame, text="<S>ave Image & Mask", command=self.handleSaveImageAndMask)
        saveImageAndMaskButton.grid(row=2, column=0)

        self.herniated = tk.BooleanVar(value=False)
        self.herniatedCheckbox = tk.Checkbutton(self.inputFrame, text="Herniate<D>", variable=self.herniated)
        self.herniatedCheckbox.grid(row=3, column=0)

        # Dataset treeview frame.
        self.datasetTreeviewFrame = DatasetTreeviewFrame(self)
        self.add(self.datasetTreeviewFrame)

    def toggleHerniated(self, event):
        self.herniated.set(not self.herniated.get())
        self.herniatedCheckbox.deselect() if not self.herniated.get() else self.herniatedCheckbox.select()
    
    def handleLoadImageIntoSAM(self):
        if globalData.currentImage is None:
            alert("Very naughty, no image available to load")
            return
        try:
            currentImageCopy = np.copy(globalData.currentImage)
            arrForSam = cv2.cvtColor(currentImageCopy.astype(np.uint8), cv2.COLOR_GRAY2RGB)
            globalData.SAM.setImage(arrForSam)
        except AttributeError as e:
            alert(f"Likely no image selected. {e}")
        globalData.imageLoaded = True

    def handleMakeMask(self):
        if not globalData.imageLoaded:
            alert("Very naughty, no image loaded!")
            return
        try:
            # Set the box.
            globalData.SAM.setBox(globalData.selectionBox)
            # Predict.
            mask = globalData.SAM.predict()
            mask = mask.astype(np.uint8)
            globalData.currentMask = mask
            globalData.currentMask = globalData.currentMask.squeeze() # Get rid of 1 in (1, x, y).
            # Display current mask atop current image.
            maskImageLabel = self.mainPanedWindow.imageFrameAndConsolePanedWindow.imageFrame.maskImageLabel
            maskImageLabel.clear()
            maskImageLabel.displayTwo(globalData.currentImage, getVisualBinaryMask(globalData.currentMask))
        except RuntimeError as e:
            alert(f"RuntimeError: Can't make mask. {e}")
        except Exception as e:
            alert(f"Error: {e}")

    def handleSaveImageAndMask(self):
        if globalData.currentMask is None:
            alert("Very naughty, no mask available to save")
            return
        globalData.currentDataset.data.append(
            Datum(
                globalData.currentImagePath,
                globalData.currentImage,
                globalData.currentMask,
                self.herniated.get()
            )
        )

        self.datasetTreeviewFrame.display()
        


class MainPanedWindow(tk.PanedWindow):
    def __init__(self, tkParent):
        super().__init__(tkParent, orient="horizontal", sashwidth=5, sashrelief=tk.RAISED)

        # First pane (left side).
        self.treeviewFrame = TreeviewFrame(self)
        self.add(self.treeviewFrame)

        # Second pane (middle).
        self.imageFrameAndConsolePanedWindow = ImageFrameAndConsolePanedWindow(self)
        self.add(self.imageFrameAndConsolePanedWindow)

        # Third pane (right side).
        self.inputFrameAndDatasetTreeviewFramePanedWindow = InputFrameAndDatasetTreeviewFramePanedWindow(self)
        self.add(self.inputFrameAndDatasetTreeviewFramePanedWindow)

        # Set initial sizes for the panes
        self.paneconfig(self.treeviewFrame, minsize=100)
        self.paneconfig(self.imageFrameAndConsolePanedWindow, minsize=100)
        self.paneconfig(self.inputFrameAndDatasetTreeviewFramePanedWindow, minsize=100)



class MainFrame(ttk.Frame):
    def __init__(self, tkParent):
        super().__init__(tkParent)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.mainPanedWindow = MainPanedWindow(self)
        self.mainPanedWindow.grid(row=0, column=0, sticky="nsew")    

    

class MaskMaker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.option_add('*tearOff', tk.FALSE) # Disable tear-off menus.
        self.geometry("1000x600")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.title("Mask Maker")

        self.menubar = tk.Menu(self)
        self["menu"] = self.menubar

        self.menuFile = tk.Menu(self.menubar)
        self.menuOptions = tk.Menu(self.menubar)

        self.menubar.add_cascade(menu=self.menuFile, label="File")
        self.menubar.add_cascade(menu=self.menuOptions, label="Options")

        self.menuFile.add_command(label='Open...', command=self.open)
        self.menuFile.add_command(label='Save', command=self.save)
        self.menuFile.add_command(label='Rename', command=self.rename)

        # Check Buttons.
        self.autoSave = tk.BooleanVar(value=False)
        self.menuOptions.add_checkbutton(label='autoSave', variable=self.autoSave, command=self.handleAutoSave)

        self.autoLoad = tk.BooleanVar(value=False)
        self.menuOptions.add_checkbutton(label='autoLoad', variable=self.autoLoad, command=self.handleAutoLoad)

        # Main Frame.
        self.mainFrame = MainFrame(self)
        self.mainFrame.grid(row=0, column=0, sticky="nsew")

        # Binds.
        inputFrameAndDatasetTreeviewFramePanedWindow = self.mainFrame.mainPanedWindow.inputFrameAndDatasetTreeviewFramePanedWindow
        self.bind("a", lambda e: inputFrameAndDatasetTreeviewFramePanedWindow.handleMakeMask())
        self.bind("s", lambda e: inputFrameAndDatasetTreeviewFramePanedWindow.handleSaveImageAndMask())
        self.bind("d", inputFrameAndDatasetTreeviewFramePanedWindow.toggleHerniated)

        self.mainloop()

    def open(self):
        filePath = filedialog.askopenfilename(
            initialdir=os.getcwd(), 
            title="Select an existing dataset", 
            filetypes=(("Dataset", "*.ds"),), 
            defaultextension=".ds"
        )
        if filePath:
            globalData.currentDatasetName = os.path.split(filePath)[1].split(".")[0]
            with open(filePath, "rb") as f:
                globalData.currentDataset = pickle.load(f)
            # Update DatasetTreeview
            self.mainFrame.mainPanedWindow.inputFrameAndDatasetTreeviewFramePanedWindow.datasetTreeviewFrame.display()

    def save(self):
        with open(f"{globalData.currentDatasetName}._backup.ds", "wb") as f:
            pickle.dump(globalData.currentDataset, f)
        with open(f"{globalData.currentDatasetName}.ds", "wb") as f:
            pickle.dump(globalData.currentDataset, f)
        notification("Saved")

    def autoSaveFunction(self):
        while globalData.autoSave:
            self.save()
            time.sleep(10)
        notification("No longer autosaving")

    def handleAutoSave(self):
        globalData.autoSave = self.autoSave.get()
        if (globalData.autoSave):
            globalData.autoSaveThread = threading.Thread(target=self.autoSaveFunction, daemon=True)
            globalData.autoSaveThread.start()
            notification("Autosaving begins")

    def handleAutoLoad(self):
        globalData.autoLoad = self.autoLoad.get()

    def rename(self):
        globalData.currentDatasetName = simpledialog.askstring("Input", "Dataset's new name:")
        self.save()
        # Update DatasetTreeview
        self.mainFrame.mainPanedWindow.inputFrameAndDatasetTreeviewFramePanedWindow.datasetTreeviewFrame.display()



MaskMaker()