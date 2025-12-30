import datetime
import re
import pytz
import streamlit as st
import pdfplumber

def name_extracor_from_pdf(input_file):
    """
    Parse PDF file and return names
    
    :param input_file: PDF file with the names
    """
    with pdfplumber.open(input_file) as pdf:
        page = pdf.pages[0]  # Open the first page
        roster_table = page.extract_table()

    # Roster_table trimming. Remove last 12 rows and 1< columns
    roster_table = roster_table[:-12]
    roster_table = [row[:1] for row in roster_table]

    # Print list of sorted names, remove blanks
    names_list = []
    for name in roster_table:
        if name[0]:  # Check if element is not empty
            names_list.append(name[0])
    names_list.sort()
    return names_list


def ics_file_creator(name, chosen_pdf):
    PERSON_NAME = name
    tzone = pytz.timezone("Pacific/Auckland")

    # Read PDF file
    with pdfplumber.open(chosen_pdf) as pdf:
        page = pdf.pages[0]
        roster_table = page.extract_table()

    # Roster_table trimming. Last 12 rows, last 3 columns
    roster_table = roster_table[:-12]
    roster_table = [row[:-3] for row in roster_table]

    ## DATA PARSING
    # Dates parsing
    dates_row = roster_table[1]

    shift_dates = [  # list of days
        datetime.datetime.strptime(date_str, "%d/%m/%Y").date()
        for date_str in dates_row[1:]  # the first cell is empty
        if date_str and re.match(r"\d{1,2}/\d{1,2}/\d{4}", str(date_str))  # date length format 1-2/1-2/4
    ]

    if len(shift_dates) < 14:
        raise ValueError("Less than two weeks presented")

    # Search for PERSON_NAME
    person_row = None
    for row in roster_table:
        if row[0] == PERSON_NAME:
            person_row = row
            break

    if not person_row:
        raise ValueError(f"{PERSON_NAME} not found")

    # Get the time for each day. Name, 14 days
    shift_tokens = person_row[1:]

    # Make shifts list
    shift_list = []

    for date, shift_time in zip(shift_dates, shift_tokens):
        if shift_time in ("OFF", ""):  # Skip days off
            continue

        # Change dots in time to colons
        shift_time = shift_time.replace(".", ":")

        if re.fullmatch(r"\d{1,2}:\d{2}-\d{1,2}:\d{2}", shift_time):  # time 1-2:1-2 - 1-2:1-2
            start_time_str, end_time_str = shift_time.split("-")  # split shift time

            # Combine shift date and time
            start_date_time = datetime.datetime.strptime(f"{date} {start_time_str}", "%Y-%m-%d %H:%M")
            end_date_time = datetime.datetime.strptime(f"{date} {end_time_str}", "%Y-%m-%d %H:%M")

            # Convert timezone
            start_date_time = tzone.localize(start_date_time)
            end_date_time = tzone.localize(end_date_time)

            # Overnight shifts. Add one day to end time.
            if end_date_time <= start_date_time:
                end_date_time += datetime.timedelta(days=1)

            shift_list.append((start_date_time, end_date_time))

    ## ICS file preparation
    def ics_dt(time_input):
        """
        Converts a datetime object to an iCalendar-compatible UTC format string.
        """
        return time_input.astimezone(pytz.UTC).strftime("%Y%m%dT%H%M%SZ")

    # ICS Header
    ics_file = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//" + PERSON_NAME + " Shift Calendar//EN"
    ]

    # Add every shift
    for start, end in shift_list:
        shift_length = round((end - start).total_seconds() / 3600, 2)
        uid = f"{start.timestamp()}-{PERSON_NAME}@roster"
        dtstamp = now_utc.strftime("%Y%m%dT%H%M%SZ")
        ics_file.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}”
            f"DTSTART:{ics_dt(start)}",
            f"DTEND:{ics_dt(end)}",
            f"SUMMARY:HK Shift {shift_length} hrs",
            f"DESCRIPTION:Shift for {PERSON_NAME}",
            "END:VEVENT"
        ])

    # ICS Footer
    ics_file.append("END:VCALENDAR")
    number_of_shifts = len(shift_list)

    # Output ICS filename
    output_ics_filename = (PERSON_NAME + "_shifts_" + dates_row[1].replace("/", "-") +
                           "_" + dates_row[-1].replace("/", "-") + ".ics")

    return (output_ics_filename, ics_file, number_of_shifts)


## Main page
# Streamlit UI
st.title("Haka shift calendar event maker")

# File upload
uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"])

if uploaded_file:
    # Extract names from the PDF
    try:
        names = name_extracor_from_pdf(uploaded_file)  # Pass the file to the extractor

        if names:
            st.write("Names found in the PDF:")

            # Display buttons in 3 columns layout
            num_buttons = len(names)
            columns = st.columns(3)  # Create 3 columns

            selected_name = None
            for i in range(0, num_buttons, 3):  # Loop through names in steps of 3
                for j, col in enumerate(columns):
                    if i + j < num_buttons:
                        name = names[i + j]
                        if col.button(name):
                            selected_name = name
                            st.session_state.selected_name = name

            if selected_name:
                try:
                    # Process the PDF with the selected name
                    ics_name, file_content, num_of_shifts = ics_file_creator(selected_name, uploaded_file)

                    # Provide a download button for the processed file
                    st.download_button(
                        label=f"Download Calendar file ({num_of_shifts} shifts)",
                        data=bytes("\n".join(file_content), "utf-8"),
                        file_name=ics_name,
                        mime="application/calendar"
                    )
                except Exception as e:
                    st.error(f"Script2: {e}")
        else:
            st.warning("No names found in the PDF.")
    except Exception as e:
        st.error(f"Script1: {e}")
