################################################################################
# This is the main program that runs the UI and instantiates other modules.
################################################################################
# -*- coding: iso-8859-1 -*-
import threading
import logging
import Queue

from Tkinter import Tk, Button, END, Frame
from ScrolledText import ScrolledText

from sigServer import SigServer


class QueueLogger(logging.Handler):
    def __init__(self, queue):
        logging.Handler.__init__(self)
        self.queue = queue

    # write in the queue
    def emit(self, record):
        self.queue.put(self.format(record).rstrip('\n') + '\n')


# noinspection SpellCheckingInspection
class SigBridgeUI(Tk):
    server = None
    server_thread = None

    def __init__(self):
        Tk.__init__(self)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # 2 rows: firts with settings, second with registrar data
        self.main_frame = Frame(self)
        # Commands row doesn't expands
        self.main_frame.rowconfigure(0, weight=0)
        # Logs row will grow
        self.main_frame.rowconfigure(1, weight=1)
        # Main frame can enlarge
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.grid(row=0, column=0)

        # Run/Stop button
        self.server_button = Button(self.main_frame, text="Connect", command=self.start_server)
        self.server_button.grid(row=0, column=0)

        # Clear button
        self.clear_button = Button(self.main_frame, text="Clear Log", command=self.clear_log)
        self.clear_button.grid(row=0, column=1)

        # Logs Widget
        self.log_widget = ScrolledText(self.main_frame)
        self.log_widget.grid(row=1, column=0, columnspan=2)
        # made not editable
        self.log_widget.config(state='disabled')

        # Queue where the logging handler will write
        self.log_queue = Queue.Queue()

        # Setup the logger
        self.uilogger = logging.getLogger('SigBridgeUI')
        self.uilogger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

        # Use the QueueLogger as Handler
        hl = QueueLogger(queue=self.log_queue)
        hl.setFormatter(formatter)
        self.uilogger.addHandler(hl)

        # self.log_widget.update_idletasks()
        self.set_geometry()

        # Setup the update_widget callback reading logs from the queue
        self.start_log()

        # Start server automatically
        self.start_server()

    def clear_log(self):
        self.log_widget.config(state='normal')
        self.log_widget.delete(0.0, END)
        self.log_widget.config(state='disabled')

    def start_log(self):
        # self.uilogger.info("SigBridge Started.")
        self.update_widget()
        # self.control_log_button.configure(text="Pause Log", command=self.stop_log)

    def update_widget(self):
        self.log_widget.config(state='normal')
        # Read from the Queue and add to the log widger
        while not self.log_queue.empty():
            line = self.log_queue.get()
            tag = "error" if " ERROR " in line else 'info'
            self.log_widget.insert(END, line, tag)
            self.log_widget.see(END)  # Scroll to the bottom
            self.log_widget.update_idletasks()
        self.log_widget.tag_config('error', foreground="red")
        self.log_widget.config(state='disabled')
        self.log_widget.after(10, self.update_widget)

    def set_geometry(self):
        # set position in window
        w = 600  # width for the Tk
        h = 300  # height for the Tk

        # get screen width and height
        ws = self.winfo_screenwidth()   # width of the screen
        hs = self.winfo_screenheight()  # height of the screen

        # calculate x and y coordinates for the Tk window
        x = (ws/2) - (w/2)
        y = (hs/2) - (h/2)

        # set the dimensions of the screen 
        # and where it is placed
        self.geometry('%dx%d+%d+%d' % (w, h, x, y))

    def start_server(self):
        try:
            self.server = SigServer(('0.0.0.0', 25), None, self.uilogger)
            self.server_thread = threading.Thread(name='server', target=self.server.run)
            self.server_thread.daemon = True
            self.server_thread.start()
            self.server_button.configure(text="Disconnect", command=self.stop_server)
        except Exception as err:
            self.uilogger.error("Cannot start the server: %s" % err.message)

        # self.label_variable.set(self.entry_variable.get()+"(Started Signal Server)")
        # self.entry.focus_set()
        # self.entry.selection_range(0, END)

    def stop_server(self):
        self.server.shutdown()
        self.server_button.configure(text="Connect", command=self.start_server)
        self.server = None
        # self.label_variable.set("Signal Server Stopped.")


if __name__ == '__main__':
    app = SigBridgeUI()
    app.title('SigBridge')
    app.mainloop()
