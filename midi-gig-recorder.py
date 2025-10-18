import rtmidi
import time
import sys
import argparse
import configparser
from threading import Lock

# --- Constants ---
# MIDI Note Names for conversion
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Lock for thread-safe printing/logging
print_lock = Lock()
# Global variables for configuration and logging
CONFIG = {}
LOG_FILE = None
VERBOSE = False
VERY_VERBOSE = False

# --- Utility Functions ---

def get_note_name(note_number):
    """Converts a MIDI note number (0-127) to a note name (e.g., C3)."""
    if 0 <= note_number <= 127:
        octave = (note_number // 12) - 1
        note = NOTE_NAMES[note_number % 12]
        return f"{note}{octave}"
    return "???"

def log_message(interface_id, output_line, raw_data=None):
    """Handles logging and console output based on verbosity levels."""
    
    # 1. Write to log file
    if LOG_FILE:
        with open(LOG_FILE, 'a') as f:
            f.write(f"[{interface_id}] {output_line}\n")
            
    # 2. Console output (Verbose mode)
    if VERBOSE:
        with print_lock:
            print(f"[{interface_id}] {output_line}")
            
    # 3. Console output (Very Verbose mode - raw data)
    if VERY_VERBOSE and raw_data is not None:
        hex_data = ' '.join(f'{b:02X}' for b in raw_data)
        with print_lock:
            print(f"[{interface_id}] RAW: {hex_data}")


# --- MIDI Parsing Callbacks ---

def parse_midi_message_1(message, time_stamp):
    """Callback for standard MIDI messages (Interface 1)."""
    
    midi_data = message[0]
    status = midi_data[0]
    msg_type = status & 0xF0
    output_line = None
    timecode = f"{time_stamp:.4f}"

    if 0x80 <= msg_type <= 0x90 and len(midi_data) >= 3:
        note_number = midi_data[1]
        velocity = midi_data[2]
        note_name = get_note_name(note_number)
        
        if msg_type == 0x80 or (msg_type == 0x90 and velocity == 0):
            output_line = f"{timecode} Note Off {note_name} <{velocity}>"
        elif msg_type == 0x90:
            output_line = f"{timecode} Note On {note_name} <{velocity}>"

    elif msg_type == 0xB0 and len(midi_data) >= 3:
        cc_number = midi_data[1]
        value = midi_data[2]
        output_line = f"{timecode} CC {cc_number} <{value}>"

    elif msg_type == 0xC0 and len(midi_data) >= 2:
        pc_value = midi_data[1]
        output_line = f"{timecode} PC <{pc_value}>"

    elif msg_type == 0xE0 and len(midi_data) >= 3:
        lsb = midi_data[1]
        msb = midi_data[2]
        pitch_value = (msb << 7) | lsb
        output_line = f"{timecode} Pitch Bend <{pitch_value}>"
        
    elif status == 0xF0:
        # System Exclusive
        if CONFIG.get('record_sysex', True):
            hex_data = ' '.join(f'{b:02X}' for b in midi_data)
            output_line = f"{timecode} Sysex {hex_data}"
        
    elif status == 0xFA:
        output_line = f"{timecode} Start"
    elif status == 0xFB:
        output_line = f"{timecode} Continue"
    elif status == 0xFC:
        output_line = f"{timecode} Stop"
    elif status == 0xF8:
        # MIDI Clock
        if CONFIG.get('record_midi_clock', False):
            output_line = f"{timecode} Clock" 
    elif status == 0xFE:
        # Active Sensing
        if CONFIG.get('record_active_sensing', False):
            output_line = f"{timecode} Active Sensing"
    
    # Fallback/Unparsed Message
    if output_line is None:
        hex_data = ' '.join(f'{b:02X}' for b in midi_data)
        output_line = f"{timecode} Unknown MIDI Message: {hex_data}"

    if output_line:
        log_message("IFACE 1", output_line, midi_data)


def parse_midi_message_2(message, time_stamp):
    """Callback for CQ18T custom messages (Interface 2)."""
    
    midi_data = message[0]
    length = len(midi_data)
    output_line = None
    timecode = f"{time_stamp:.4f}"
    
    try:
        if length == 9:
            # 9 bytes: Mute Toggle (B0 63 MSB B0 62 LSB B0 60 00)
            if (midi_data[0] == 0xB0 and midi_data[1] == 0x63 and 
                midi_data[3] == 0xB0 and midi_data[4] == 0x62 and 
                midi_data[6] == 0xB0 and midi_data[7] == 0x60 and midi_data[8] == 0x00):
                
                ch_msb = midi_data[2]
                ch_lsb = midi_data[5]
                output_line = (f"{timecode} CQ18T Mute Toggle "
                               f"Address (CC99/98): {ch_msb:02X}/{ch_lsb:02X}")

        elif length == 12:
            # 12 bytes: Mute On/Off or Level
            if (midi_data[0] == 0xB0 and midi_data[1] == 0x63 and 
                midi_data[3] == 0xB0 and midi_data[4] == 0x62 and 
                midi_data[6] == 0xB0 and 
                midi_data[8] == 0xB0 and midi_data[9] == 0x26):
                
                ch_msb = midi_data[2]
                ch_lsb = midi_data[5]
                data_msb = midi_data[7]
                data_lsb = midi_data[10]
                
                if data_msb == 0x00: # Mute On/Off
                    action = "Mute On" if data_lsb == 0x01 else ("Mute Off" if data_lsb == 0x00 else "Unknown Mute Value")
                    output_line = (f"{timecode} CQ18T {action} "
                                   f"Address (CC99/98): {ch_msb:02X}/{ch_lsb:02X}")
                
                else: # Level/Fader
                    level_value = (data_msb << 7) | data_lsb
                    output_line = (f"{timecode} CQ18T Level (NRPN Data) <{level_value}> "
                                   f"Address (CC99/98): {ch_msb:02X}/{ch_lsb:02X} "
                                   f"Raw Value (CC6/38): {data_msb:02X}/{data_lsb:02X}")

        # Unrecognized Sysex/Real-Time (though these should be filtered by rtmidi ignore_types)
        elif status == 0xF0 and CONFIG.get('record_sysex', True):
            hex_data = ' '.join(f'{b:02X}' for b in midi_data)
            output_line = f"{timecode} Sysex {hex_data}"
            
        # Fallback for unparsed messages
        if output_line is None:
            hex_data = ' '.join(f'{b:02X}' for b in midi_data)
            output_line = f"{timecode} CQ18T Unrecognized ({length} bytes): {hex_data}"
    
    except IndexError:
        hex_data = ' '.join(f'{b:02X}' for b in midi_data)
        output_line = f"{timecode} CQ18T Incomplete/Bad Message: {hex_data}"
    
    if output_line:
        log_message("IFACE 2", output_line, midi_data)


# --- Port Selection and Main Logic ---

def select_port(midiin, keyword):
    """Allows user to select a port based on a keyword."""
    ports = midiin.get_ports()
    if not ports:
        print("❌ No MIDI input ports found.")
        return None

    print(f"\nAvailable MIDI input ports (Search Keyword: '{keyword}'):")
    
    selected_port = -1
    for i, port in enumerate(ports):
        print(f"  [{i}] {port}")
        if keyword.lower() in port.lower():
            selected_port = i
    
    if selected_port != -1:
        print(f"Auto-selected port [{selected_port}] for '{keyword}'.")
        return selected_port
    
    print(f"\nCould not auto-select port for '{keyword}'. Please enter the number manually:")
    
    while True:
        try:
            choice = input(f"Select port number for '{keyword}': ")
            port_index = int(choice)
            if 0 <= port_index < len(ports):
                return port_index
            else:
                print("Invalid number. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number.")

def list_ports():
    """Prints a list of all available MIDI input ports."""
    midiin = rtmidi.MidiIn()
    ports = midiin.get_ports()
    if not ports:
        print("No MIDI input ports found.")
        return

    print("\n--- Available MIDI Input Ports ---")
    for i, port in enumerate(ports):
        print(f"  [{i}] {port}")
    print("----------------------------------\n")
    sys.exit(0)

def load_config(config_file):
    """Loads configuration from the specified file."""
    config = configparser.ConfigParser()
    try:
        config.read(config_file)
    except Exception as e:
        print(f"❌ Error reading configuration file '{config_file}': {e}")
        sys.exit(1)

    global CONFIG
    
    # Load Ports
    CONFIG['interface_1_keyword'] = config.get('PORTS', 'interface_1_keyword', fallback='Standard MIDI')
    CONFIG['interface_2_keyword'] = config.get('PORTS', 'interface_2_keyword', fallback='CQ18T')

    # Load Filters and convert to boolean
    CONFIG['record_midi_clock'] = config.getboolean('FILTERS', 'record_midi_clock', fallback=False)
    CONFIG['record_active_sensing'] = config.getboolean('FILTERS', 'record_active_sensing', fallback=False)
    # The rtmidi default is to filter sysex, we explicitly invert the setting here
    CONFIG['record_sysex'] = config.getboolean('FILTERS', 'record_sysex', fallback=True)
    
    print(f"Configuration loaded from {config_file}.")


def main():
    """Main function to initialize and run the MIDI recorder."""
    
    # 1. Argument Parsing
    parser = argparse.ArgumentParser(description="Two-Interface MIDI Traffic Recorder with custom parsing.")
    parser.add_argument('-c', '--config', type=str, default='config.ini',
                        help="Specify the configuration file (default: config.ini).")
    parser.add_argument('-l', '--log', type=str,
                        help="Specify the filename/path for the MIDI record file. If omitted, no file is written.")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="Enable verbose mode: display all received messages as formatted text (as they are logged).")
    parser.add_argument('-vv', '--very-verbose', action='store_true',
                        help="Enable very verbose mode: display formatted text AND raw hexadecimal data for all messages.")
    parser.add_argument('-p', '--ports', action='store_true',
                        help="List all available MIDI Input ports and exit.")
    
    args = parser.parse_args()

    if args.ports:
        list_ports()
        
    # Set global options
    global LOG_FILE, VERBOSE, VERY_VERBOSE
    LOG_FILE = args.log
    VERBOSE = args.verbose
    VERY_VERBOSE = args.very_verbose
    
    # Load configuration
    load_config(args.config)

    # --- Initialise MIDI ---
    midiin = rtmidi.MidiIn()
    
    # --- Port 1 Setup (Standard MIDI) ---
    port_1_index = select_port(midiin, CONFIG['interface_1_keyword'])
    if port_1_index is None:
        sys.exit(1)

    port_1_name = midiin.get_port_name(port_1_index)
    midi_in_1 = rtmidi.MidiIn()
    midi_in_1.open_port(port_1_index)
    
    # rtmidi.ignore_types(sysex, midi_clock, active_sensing)
    # We invert the config logic here because ignore_types expects a boolean for 'ignore'
    ignore_sysex = not CONFIG['record_sysex']
    ignore_clock = not CONFIG['record_midi_clock']
    ignore_sense = not CONFIG['record_active_sensing']
    
    midi_in_1.ignore_types(ignore_sysex, ignore_clock, ignore_sense)
    midi_in_1.set_callback(parse_midi_message_1)
    
    print(f"\n✅ Opened Interface 1: {port_1_name}. Recording standard MIDI traffic.")

    # --- Port 2 Setup (CQ18T) ---
    port_2_index = select_port(midiin, CONFIG['interface_2_keyword'])
    if port_2_index is None:
        sys.exit(1)
        
    port_2_name = midiin.get_port_name(port_2_index)
    midi_in_2 = rtmidi.MidiIn() 
    midi_in_2.open_port(port_2_index)
    
    midi_in_2.ignore_types(ignore_sysex, ignore_clock, ignore_sense)
    midi_in_2.set_callback(parse_midi_message_2)
    
    print(f"✅ Opened Interface 2: {port_2_name}. Recording CQ18T custom messages.")
    
    if LOG_FILE:
        print(f"📝 Logging to file: {LOG_FILE}")
        
    if VERBOSE or VERY_VERBOSE:
        print("👀 Verbose logging ENABLED.")
    
    print("\n--- MIDI Recording Started (Press Ctrl+C to stop) ---")

    try:
        # Keep the script running to receive messages via the callback function
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n--- Recording Stopped ---")
    finally:
        # Clean up
        midi_in_1.close_port()
        midi_in_2.close_port()
        del midi_in_1
        del midi_in_2
        del midiin

if __name__ == '__main__':
    main()
    
 