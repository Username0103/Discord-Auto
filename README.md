# Discord-Auto

A Python-based Discord message scraper that automatically logs into Discord accounts and extracts message data from specified servers and channels. This tool uses Selenium WebDriver to automate Discord's web interface and collect conversation history for analysis or archival purposes.

## Features

- **Automated Discord Login**: Securely logs into Discord using credentials from environment variables
- **Message Scraping**: Extracts complete message histories from specified channels and servers
- **Data Export**: Saves collected messages in JSON or CSV format for analysis
- **Resume Capability**: Can continue scraping from where it left off using saved state
- **Typing Simulation**: Includes realistic typing patterns with configurable WPM and typo rates
- **Stealth Mode**: Uses selenium-stealth to avoid detection

## Installation

1. Clone the repository:
```bash
git clone https://github.com/Username0103/Discord-Auto.git
cd Discord-Auto
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your environment variables by creating a `.env` file:
```
discord_email=your_email@example.com
discord_pass=your_password
target_server_name=ServerName
target_channel_id=123456789
```

## Requirements

- Python 3.7+
- Chrome/Chromium browser

## Usage

1. Configure your `.env` file with your Discord credentials and target server information
2. Run the scraper:
```bash
python main.py
```

3. The tool will automatically:
   - Log into Discord using your credentials
   - Navigate to the specified server and channel
   - Begin scraping messages and saving them to a file
   - Continue until interrupted with Ctrl+C

## Configuration Options

The script includes several configuration options at the top of `main.py`:

- `SKIP_INVALID`: Skip messages with missing data
- `SAVING_INTERVAL_SECONDS`: Delay between save operations
- `WRITING_MODE`: Choose between "json" or "csv" output format
- `SAVING_PATH`: Directory to save scraped data
- `ERROR_SCREENSHOT_PATH`: Location for error screenshots

## How It Works

1. **Authentication**: Uses Selenium to automate Discord login through the web interface
2. **Navigation**: Automatically navigates to specified Discord servers and channels
3. **Message Extraction**: Scrapes message content, timestamps, author information, and metadata
4. **Data Processing**: Filters and deduplicates messages before saving
5. **Export**: Saves data in structured JSON or CSV format for further analysis
6. **Contains Easter Egg**: Though considering how short the script is it takes like 5 seconds to find it.

## Output Data Structure

The scraper extracts the following message data:
- Author name and ID
- Message content and timestamp
- Server and channel information
- Reply status and message threading

## Legal and Ethical Considerations

Discord scraping tools operate in a legal gray area. Key considerations include:

- **Terms of Service**: Discord's ToS prohibits automated data collection.
- **Privacy Laws**: Collecting user messages may violate GDPR and other privacy regulations.
- **Account Risk**: Using automation tools may result in account suspension.

## Disclaimer

This software is provided "as is" under the MIT License. The developers are not responsible for any misuse of this tool or consequences resulting from its use. Users are solely responsible for ensuring their use complies with applicable laws.
