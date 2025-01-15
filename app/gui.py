import sys
import os
import subprocess
import re

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QComboBox,
    QToolButton, QMenu, QFileDialog, QProgressBar, QLabel, QTextEdit,
    QHBoxLayout, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTranslator, QLocale
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices


# ---------------- Helper function to get audio file duration ---------------
def get_audio_duration(file_path):
    """
    Returns the duration in seconds, e.g., 123.45.
    Requires ffprobe in PATH.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
    return float(output)


# ---------------- Thread class to run Whisper subprocess ---------------
class SubprocessThread(QThread):
    line_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    progress_signal = pyqtSignal(float)  # signal for passing the progress %

    def __init__(self, file_path, model_name, output_format, duration_sec, language_code):
        super().__init__()
        self.file_path = file_path
        self.model_name = model_name
        self.output_format = output_format
        self.duration_sec = duration_sec  # audio file duration in seconds
        self.current_lang = language_code  # Store the current language code

    def run(self):
        import re
        import subprocess, sys

        self.line_signal.emit(self.tr("Loading Whisper model, please wait a moment..."))
        
        cmd = [
            sys.executable,
            "-u",  # unbuffered
            "app/worker_transcribe.py",
            self.file_path,
            self.model_name,
            self.output_format,
            self.current_lang  # Pass the current language code
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
        except Exception as e:
            self.line_signal.emit(f"{QCoreApplication.translate('SubprocessThread', 'Error launching subprocess:')} {e}")
            self.finished_signal.emit()
            return

        time_pattern = re.compile(
            r"\[(\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}:\d{2}\.\d{3})\]"
        )
        
        start_output = False

        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break

            if line:
                # When we detect 'Detected language:' or timestamp, it's worth showing the log
                match = time_pattern.search(line)
                if "Detected language:" in line or match:
                    start_output = True

                if start_output:
                    self.line_signal.emit(line.rstrip("\n"))

                    # Calculate progress based on the timestamp
                    if match and self.duration_sec:
                        end_time_str = match.group(2)
                        end_time_seconds = self.hms_to_seconds(end_time_str)
                        progress_percent = (end_time_seconds / self.duration_sec) * 100
                        self.progress_signal.emit(progress_percent)

        proc.wait()
        self.finished_signal.emit()

    def hms_to_seconds(self, hms_str):
        """Converts 'HH:MM:SS.xxx' or 'MM:SS.xxx' to float seconds."""
        parts = hms_str.split(":")
        if len(parts) == 2:
            # "MM:SS.xxx"
            minutes = int(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds
        elif len(parts) == 3:
            # "HH:MM:SS.xxx"
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        return 0


# ---------------- Main window class ---------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        
        # Translator (single, global in MainWindow)
        self.translator = QTranslator()  # Initialize the translator before use
        
        # Initialize and configure all GUI elements
        
        # Window title
        self.setWindowTitle(self.tr("mai | Offline Transcriber"))

        # Main layout
        self.main_layout = QVBoxLayout()

        # ---- Language bar (QToolButton + QMenu) ----
        self.top_bar_layout = QHBoxLayout()
        self.lang_button = QToolButton()
        self.lang_button.setText("PL")  # Default
        self.lang_menu = QMenu()
        self.lang_pl_action = QAction("Polski", self)
        self.lang_en_action = QAction("English", self)
        self.lang_menu.addAction(self.lang_pl_action)
        self.lang_menu.addAction(self.lang_en_action)
        self.lang_button.setMenu(self.lang_menu)
        self.lang_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.lang_button.setStyleSheet("""
            QToolButton {
                padding: 4px 12px 4px 0;                
                color: #555;
                background-color: #F0F0F0;
                border: 1px solid #CCC;
                border-radius: 6px;  /* Rounded corners */
            }
            QToolButton::menu-indicator {
                subcontrol-position: right center;
                subcontrol-origin: padding;
                padding-right: 0;
                margin-right: 6px;
                width: 5px;
                height: 5px;
                overflow: hidden;
            }
            """)

        # Connect signals for language switching
        self.lang_pl_action.triggered.connect(lambda: self.change_language("pl"))
        self.lang_en_action.triggered.connect(lambda: self.change_language("en"))

        # Add buttons to top_bar
        self.top_bar_layout.addStretch()
        self.top_bar_layout.addWidget(self.lang_button)

        # Add top_bar to main layout
        self.main_layout.addLayout(self.top_bar_layout)

        # ---- Input file group ----
        self.file_group_box = QGroupBox(self.tr("Input file"))
        self.file_group_box_layout = QVBoxLayout()

        # Label with file path (default "No file selected")
        self.file_label = QLabel(self.tr("No file selected"))
        self.file_label.setWordWrap(True)
        self.file_group_box_layout.addWidget(self.file_label)

        self.file_group_box.setLayout(self.file_group_box_layout)
        self.file_group_box.setStyleSheet("""
            QGroupBox {
                font-weight: normal;
                border: 1px solid #CCC;
                border-radius: 5px;
                margin-top: 6px;
                color: #555;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: #555;
            }
        """)

        self.main_layout.addWidget(self.file_group_box)

        # ---- Button to choose the file ----
        self.btn_choose_file = QPushButton(self.tr("Choose audio/video file"))
        self.btn_choose_file.clicked.connect(self.choose_file)
        self.main_layout.addWidget(self.btn_choose_file)

        # ---- ComboBox: model selection ----
        self.model_box = QComboBox()
        # First item - message "Select Whisper model"
        self.model_box.addItem(self.tr("Select Whisper model"))
        # self.model_box.addItems(["tiny", "base", "small", "medium", "large"])
        self.model_box.addItem(self.tr("tiny - smallest model (low accuracy)"), "tiny")
        # self.model_box.addItem("base model", "base") # Removed base model
        self.model_box.addItem(self.tr("small - small model (medium accuracy)"), "small")
        self.model_box.addItem(self.tr("medium - medium model (high accuracy)"), "medium")
        self.model_box.addItem(self.tr("large - large model (highest accuracy)"), "large")
        
        self.main_layout.addWidget(self.model_box)

        # ---- ComboBox: output format selection ----
        self.format_box = QComboBox()
        # First item - message "Select output format"
        self.format_box.addItem(self.tr("Select output format"))
        # self.format_box.addItems([".srt", ".txt"])
        self.format_box.addItem(self.tr(".txt - text file"), ".txt")
        self.format_box.addItem(self.tr(".srt - movie subtitles"), ".srt")
        self.main_layout.addWidget(self.format_box)

        # ---- Start button ----
        self.btn_start = QPushButton(self.tr("Start transcription"))
        self.btn_start.clicked.connect(self.start_transcription)
        self.btn_start.setEnabled(False)  # disabled by default
        self.main_layout.addWidget(self.btn_start)

        # ---- Progress bar ----
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.main_layout.addSpacing(0)
        self.main_layout.addWidget(self.progress)
        self.main_layout.addSpacing(5)

        # ---- Text area for logs ----
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setFixedHeight(200)
        self.main_layout.addWidget(self.text_area)

        # ---- Status label ----
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.main_layout.addWidget(self.status_label)

        # ---- Button to open the output file ----
        self.btn_open_file = QPushButton(self.tr("Open Transcription File"))
        self.btn_open_file.clicked.connect(self.open_output_file)
        self.btn_open_file.setEnabled(False)  # Disabled by default
        
        self.btn_open_file.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 4px 8px;
                margin-bottom: 0;
            }

            /* Hover effect */
            QPushButton:hover {
                background-color: #45a049;
            }

            /* Disabled button effect */
            QPushButton:disabled {
                background-color: #F1F1F1;
                color: #aaa;
                border: 1px solid #CCC;
            }
            """)
        self.main_layout.addWidget(self.btn_open_file)
        
        self.setLayout(self.main_layout)
        self.setFixedWidth(400)

        # Thread = None
        self.thread = None

        # Connect signals to ComboBoxes to enable/disable the Start button
        self.model_box.currentIndexChanged.connect(self.update_start_button_state)
        self.format_box.currentIndexChanged.connect(self.update_start_button_state)

        # Initialize current language
        self.current_lang = "en"  # Default to English
        self.auto_load_system_locale()  # Load and set system locale
        
        # Path to output file
        self.output_file_path = None


    # ---------------- Translation handling ----------------
    def auto_load_system_locale(self):
        """ Loads the default translator for the system language. """
        code = QLocale.system().name()[:2]  # e.g., 'en' or 'pl'
        self.change_language(code)

    def change_language(self, code):
        """
        Method to switch the translator to a given language code ('en', 'pl', etc.)
        Assumes that in the 'translations' directory we have files pl.qm, en.qm etc.
        """
        self.current_lang = code  # Update current language

        base_dir = os.path.dirname(os.path.abspath(__file__))
        translations_dir = os.path.join(base_dir, "..", "translations")
        qm_file = os.path.join(translations_dir, f"{code}.qm")

        # First remove the previous translator (if any)
        app = QApplication.instance()
        app.removeTranslator(self.translator)

        # Try to load the new translator
        if os.path.exists(qm_file) and self.translator.load(qm_file):
            app.installTranslator(self.translator)
            if code == "pl":
                self.lang_button.setText("PL")
            else:
                self.lang_button.setText("EN")
        else:
            # If no translation file, set language to EN
            self.lang_button.setText("EN")

        # Now refresh all texts
        self.retranslate_ui()

    def retranslate_ui(self):
        """
        Manually setting all texts using self.tr("...").
        (After reloading the translator.)
        """
        self.setWindowTitle(self.tr("mai | Offline Transcriber"))
        
        # Title of groupBox
        self.file_group_box.setTitle(self.tr("Input file"))
        
        # File label (translate regardless of the current state)
        if self.file_label.text() in [self.tr("No file selected"), "No file selected", self.tr("Nie wybrano pliku"), "Nie wybrano pliku"]:
            self.file_label.setText(self.tr("No file selected")) 

        self.btn_choose_file.setText(self.tr("Choose audio/video file"))

        # ComboBox model
        first_model_text = self.tr("Select Whisper model")
        if self.model_box.itemText(0) != first_model_text:
            self.model_box.setItemText(0, first_model_text)
        
        # Update the rest of model_box elements
        if self.model_box.count() > 1:
            self.model_box.setItemText(1, self.tr("tiny - smallest model (low accuracy)"))
        if self.model_box.count() > 2:
            self.model_box.setItemText(2, self.tr("small - small model (medium accuracy)"))
        if self.model_box.count() > 3:
            self.model_box.setItemText(3, self.tr("medium - medium model (high accuracy)"))
        if self.model_box.count() > 4:
            self.model_box.setItemText(4, self.tr("large - large model (highest accuracy)"))

        # ComboBox format
        first_format_text = self.tr("Select output format")
        if self.format_box.itemText(0) != first_format_text:
            self.format_box.setItemText(0, first_format_text)
        if self.format_box.count() > 1:
            self.format_box.setItemText(1, self.tr(".txt - text file"))
        if self.format_box.count() > 2:
            self.format_box.setItemText(2, self.tr(".srt - movie subtitles"))

        self.btn_start.setText(self.tr("Start transcription"))
        # Translate the button to open the output file
        self.btn_open_file.setText(self.tr("Open Transcription File"))
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #0380F6;
                color: white;
                font-weight: normal;
                border: none;
                border-radius: 6px;
                padding: 4px 8px;
                margin-bottom: 0;
            }

            /* Hover effect */
            QPushButton:hover {
                background-color: #0378E6;
            }

            /* Disabled button effect */
            QPushButton:disabled {
                background-color: #F1F1F1;
                color: #aaa;
                border: 1px solid #CCC;
            }
            """)

        self.adjustSize()

    # ---------------- UI Logic ----------------
    def choose_file(self):
        file_dialog = QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(
            self,
            self.tr("Choose audio/video file"),  # Window title
            "",
            "Audio/Video Files (*.3gp *.aac *.ac3 *.aiff *.amr *.ape *.au *.flac "
            "*.m4a *.m4b *.mka *.mp3 *.mp4 *.mpg *.mpeg *.oga *.ogg *.opus *.spx "
            "*.tta *.wav *.webm *.wma *.wmv *.avi *.mov *.mkv);;All Files (*)"
        )
        if file_path:
            self.file_label.setText(file_path)
            self.adjustSize()
        else:
            # If no file is chosen, set label to "No file selected"
            self.file_label.setText(self.tr("No file selected"))
            
        self.file_label.setStyleSheet("""
            QLabel {
                color: #777;
                font-style: regular;  /* if you want a slightly slanted font */
            }
            """)

        self.btn_open_file.setEnabled(False)  # Disable the open output file button
        self.update_start_button_state()

    def update_start_button_state(self):
        file_selected = (self.file_label.text() not in [self.tr("No file selected"), "No file selected"])
        model_selected = (self.model_box.currentIndex() > 0)
        format_selected = (self.format_box.currentIndex() > 0)
        self.btn_start.setEnabled(file_selected and model_selected and format_selected)


    def start_transcription(self):
        file_path = self.file_label.text()
        # If still "No file selected" - abort
        if file_path in [self.tr("No file selected"), "No file selected"]:
            self.status_label.setText(self.tr("Please choose a file first!"))
            return

        model_name = self.model_box.currentData()
        output_format = self.format_box.currentData()

        self.status_label.setText(self.tr("Transcription in progress..."))
        self.text_area.clear()
        self.progress.setRange(0, 100)

        # Calculating path to output file
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        self.output_file_path = os.path.join(os.path.dirname(file_path), base_name + output_format)

        self.btn_open_file.setEnabled(False)  # Disable the open output file button
        self.btn_start.setEnabled(False) # Disable the start button
    
        # Get the audio file duration (e.g., from ffprobe)
        duration_sec = get_audio_duration(file_path)

        # Initialize the thread passing the language code
        self.thread = SubprocessThread(
            file_path,
            model_name,
            output_format,
            duration_sec,
            self.current_lang  # Pass the current language code
        )
        self.thread.line_signal.connect(self.update_messages)
        self.thread.progress_signal.connect(self.update_progress)
        self.thread.finished_signal.connect(self.on_finished)
        self.adjustSize()
        self.thread.start()

    def update_messages(self, message):
        self.text_area.append(message)
        self.text_area.ensureCursorVisible()

    def update_progress(self, value):
        self.progress.setValue(int(value))

    def on_finished(self):
        self.status_label.setText(self.tr("Transcription finished."))
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.adjustSize()

        self.btn_start.setEnabled(True)  # Enable the start button
        
        # Check if the output file exists
        if self.output_file_path and os.path.exists(self.output_file_path):
            self.btn_open_file.setEnabled(True)
        else:
            self.btn_open_file.setEnabled(False)
            self.status_label.setText(self.tr("Transcription completed, but the output file was not found."))

    def open_output_file(self):
        if self.output_file_path and os.path.exists(self.output_file_path):
            url = QUrl.fromLocalFile(self.output_file_path)
            if QDesktopServices.openUrl(url):
                self.status_label.setText(self.tr("Transcription file opened successfully."))
            else:
                self.status_label.setText(self.tr("Failed to open the transcription file."))
        else:
            self.status_label.setText(self.tr("The transcription file is not available."))


