/***
 * StreamDock KWin Window Detector
 * 
 * This script is loaded into KWin's scripting engine to query the active window.
 * It prints the window title and resource class to the system journal/stdout,
 * where it can be read by the main application.
 * 
 * Usage:
 * The script expects a global variable or text replacement for 'MARKER_ID'
 * to uniquely identify the log entry.
 ***/

var active = workspace.activeWindow;
var result = "None|None";

if (active) {
    // Escape pipes if necessary, though resourceClass usually doesn't have them
    var caption = active.caption.split('|').join(' ');
    var cls = active.resourceClass;
    result = caption + "|" + cls;
}

print("MARKER_ID:" + result);
