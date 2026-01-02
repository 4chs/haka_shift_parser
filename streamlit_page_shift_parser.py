import datetime
import re
import pytz
import streamlit as st
import pdfplumber

def remove_rows(data_table):
    """
    Trims table by removing non-relevant columns and rows.
    :param data_table: list of lists. 
    """
    # Remove right columns, leaving only names and dates
    data_table = [row[:15] for row in data_table]
    # Remove technocal row among names
    data_table = [row for row in data_table if row[0] != "Hours ALL / HK"]
    # Remove last techniocal rows
    for column, row in enumerate(data_table):
        if row[0] == "Laundry & Public Areas":  # Check if the first index matches the value
            data_table = data_table[:column]  # Exclude row and latter rows
    return data_table

def name_extracor_from_pdf(input_file):
    """
    Parses PDF file and returns names
    :param input_file: PDF file with the names
    """
    with pdfplumber.open(input_file) as pdf:
        page = pdf.pages[0]  # Open the first page
        roster_table = page.extract_table()

    # Roster_table trimming.
    roster_table = remove_rows (roster_table)

    # Print list of sorted names, remove blanks
    names_list = []
    for person_name in roster_table:
        if person_name[0]:  # Check if element is not empty
            names_list.append(person_name[0])
    names_list.sort()
    return names_list


def ics_file_creator(input_name, chosen_pdf):
    person_name = input_name
    tzone = pytz.timezone("Pacific/Auckland")

    # Read PDF file
    with pdfplumber.open(chosen_pdf) as pdf:
        page = pdf.pages[0]
        roster_table = page.extract_table()

    # Roster_table trimming.
    roster_table = remove_rows (roster_table)

    ## DATA PARSING
    # Dates parsing
    dates_row = roster_table[1]

    shift_dates = [  # list of days
        datetime.datetime.strptime(date_str, "%d/%m/%Y").date()
        for date_str in dates_row[1:]  # the first cell is empty
        if date_str and re.match(r"\d{1,2}/\d{1,2}/\d{4}", str(date_str))  # date format 1-2/1-2/4
    ]

    if len(shift_dates) < 14:
        raise ValueError("Less than two weeks presented")

    # Search for person_name
    person_row = None
    for row in roster_table:
        if row[0] == person_name:
            person_row = row
            break

    if not person_row:
        raise ValueError(f"{person_name} not found")

    # Get the time for each day. Name, 14 days
    shift_tokens = person_row[1:]

    # Make list of shifts
    shift_list = []
    for each_shift in range(len(shift_dates)):
        date = shift_dates[each_shift]
        shift_time = shift_tokens[each_shift]

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
        "PRODID:-//" + person_name + " Shift Calendar//EN"
    ]
    now_utc = datetime.datetime.now(pytz.utc)
    # Add every shift
    for start, end in shift_list:
        shift_length = round((end - start).total_seconds() / 3600, 2)
        uid = f"{start.timestamp()}-{person_name}@roster"
        dtstamp = now_utc.strftime("%Y%m%dT%H%M%SZ")
        ics_file.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{ics_dt(start)}",
            f"DTEND:{ics_dt(end)}",
            f"SUMMARY:HK Shift {shift_length} hrs",
            f"DESCRIPTION:Shift for {person_name}",
            "END:VEVENT"
        ])

    # ICS Footer
    ics_file.append("END:VCALENDAR")
    number_of_shifts = len(shift_list)

    # Output ICS filename
    output_ics_filename = (person_name + "_shifts_" + dates_row[1].replace("/", "-") +
                           "_" + dates_row[-1].replace("/", "-") + ".ics")

    return (output_ics_filename, ics_file, number_of_shifts)


## Main page
# Streamlit UI
st.set_page_config(page_title="🏨 Haka House Shifter")
st.title("Haka shift calendar event maker")

uploaded_file = st.file_uploader(
    "Upload a shift roster PDF file",
    type=["pdf"]
)

if uploaded_file:
    try:    # Get names from PDF file
        names = name_extracor_from_pdf(uploaded_file)
        if names:
            st.write("Click a name to download their calendar:")
            # Make download buttons for each name
            for i in range(0, len(names), 3):
                # Create 3 columns
                cols = st.columns(3)
                # Get the names for the current row
                row_names = names[i : i + 3]
                for index, name in enumerate(row_names):
                    try:
                        # Get calendar files for each name
                        ics_name, file_content, num_of_shifts = ics_file_creator(name, uploaded_file)
                        # Button creation
                        cols[index].download_button(
                            label=f"{name} ({num_of_shifts})",
                            data="\n".join(file_content).encode("utf-8"),
                            file_name=ics_name,
                            mime="text/calendar",
                            key=f"download_{name}",
                            use_container_width=True  # Adjust the width
                        )
                    except Exception as e:
                        cols[index].error(f"Error processing name: {name}")
        else:
            st.warning("No names found in the PDF.")
    except Exception as e:
        st.error(f"PDF processing error: {e}")
