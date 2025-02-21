import dearpygui.dearpygui as dpg
import requests
from bs4 import BeautifulSoup
import time
import yfinance as yf
import plotly.graph_objects as go
import numpy as np
from PIL import Image
import io
from datetime import timedelta
import pytz  # Add this import at the top

# Initialize global variables
ticker_data = {}
last_update_time = "Never"
current_sort = {'field': 'mentions', 'reverse': True}  # Default sort by mentions descending

def create_plot(prices, timestamps, ticker):
    """Creates a Plotly figure"""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps,
        y=prices,
        mode='lines',
        name=ticker,
        line=dict(width=1)
    ))
    
    fig.update_layout(
        height=300,
        width=500,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(128,128,128,0.2)',
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor='rgba(128,128,128,0.2)',
            type='date',
            tickformat='%H:%M\n%m/%d'
        ),
        showlegend=False
    )
    return fig

def fig_to_rgba_array(fig):
    """Converts a plotly figure to an RGBA array for DPG texture"""
    img_bytes = fig.to_image(format="png")
    img = Image.open(io.BytesIO(img_bytes))
    img_array = np.array(img)
    if img_array.shape[2] == 3:
        alpha = np.full((*img_array.shape[:2], 1), 255, dtype=np.uint8)
        img_array = np.concatenate([img_array, alpha], axis=2)
    return img_array.flatten().tolist()

def fetch_stock_data(ticker):
    """Fetches detailed stock data using yfinance"""
    try:
        clean_ticker = ticker.replace('$', '')
        stock = yf.Ticker(clean_ticker)
        hist = stock.history(period="5d", interval="15m")
        if len(hist) > 0:
            return hist['Close'].tolist(), hist.index.tolist()
        return None, None
    except Exception as e:
        print(f"Error fetching stock data for {clean_ticker}: {e}")
        return None, None

def fetch_apewisdom_data():
    """Scrapes top 10 tickers from ApeWisdom.io"""
    url = "https://apewisdom.io/"
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        raw_data = [div.text.strip() for div in soup.find_all("td", class_="td-right")[:30]]
        
        sentiments = []
        for span in soup.find_all("span", class_=["percentage-green", "percentage-red"]):
            try:
                sentiment = float(span.text.strip().rstrip('%'))
                sentiments.append(sentiment)
            except ValueError:
                sentiments.append(0.0)
        
        ticker_data = []
        sentiment_idx = 0
        for i in range(0, len(raw_data), 3):
            if i + 2 < len(raw_data):
                ticker = raw_data[i + 1]
                mentions = raw_data[i + 2]
                
                if ticker.isdigit():
                    continue
                
                sentiment = sentiments[sentiment_idx] if sentiment_idx < len(sentiments) else 0.0
                sentiment_idx += 1
                
                ticker_data.append({
                    'ticker': ticker,
                    'mentions': mentions,
                    'sentiment_change': sentiment
                })
        
        return ticker_data[:10]
        
    except Exception as e:
        print(f"Error fetching ApeWisdom data: {e}")
        return None

def update_data():
    """Fetches and updates ticker data."""
    global ticker_data, last_update_time
    dpg.configure_item("loading_wheel", show=True)
    
    ape_data = fetch_apewisdom_data()
    if not ape_data:
        dpg.set_value("status_text", "Error fetching tickers from ApeWisdom!")
        dpg.configure_item("loading_wheel", show=False)
        return
    
    ticker_data.clear()
    
    for item in ape_data:
        ticker = item['ticker']
        prices, timestamps = fetch_stock_data(ticker)
        
        if prices and timestamps:
            current_price = prices[-1]
            prev_price = prices[0]
            price_change = ((current_price - prev_price) / prev_price) * 100
            
            ticker_data[ticker] = {
                'prices': prices,
                'timestamps': timestamps,
                'price_change': price_change,
                'sentiment_change': item['sentiment_change'],
                'mentions': item['mentions']
            }
        else:
            print(f"Error fetching data for {ticker}")
            ticker_data[ticker] = "Error fetching data"
    
    last_update_time = time.time()
    refresh_ui()
    dpg.configure_item("loading_wheel", show=False)

def get_time_since_update():
    """Returns time since last update in minutes and seconds"""
    if last_update_time == "Never":
        return "Never"
    elapsed = time.time() - last_update_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    return f"{minutes}m {seconds}s ago"

def get_color_from_percentage(percentage):
    """Returns RGB color based on percentage change"""
    if percentage > 0:
        intensity = min(abs(percentage) / 20.0, 1.0)
        return [0, intensity, 0]
    else:
        intensity = min(abs(percentage) / 20.0, 1.0)
        return [intensity, 0, 0]

def sort_tickers(field):
    """Updates the sort settings and refreshes the UI"""
    global current_sort
    if current_sort['field'] == field:
        # If clicking same field, toggle direction
        current_sort['reverse'] = not current_sort['reverse']
    else:
        # New field, default to descending
        current_sort['field'] = field
        current_sort['reverse'] = True
    refresh_ui()

def sorted_ticker_data():
    """Returns ticker data sorted according to current settings"""
    def get_sort_key(item):
        ticker, data = item
        if isinstance(data, str):
            return -float('inf')  # Put errors at the end
        try:
            if current_sort['field'] == 'mentions':
                return float(str(data['mentions']).replace(',', ''))
            return float(data[current_sort['field']])
        except (ValueError, KeyError):
            return -float('inf')
    
    items = list(ticker_data.items())
    return sorted(items, key=get_sort_key, reverse=current_sort['reverse'])

def refresh_ui():
    """Updates the UI with current ticker data"""
    try:
        children = dpg.get_item_children("ticker_list")
        if children and len(children) > 1:
            for child in children[1]:
                dpg.delete_item(child)
        
        # Add sorting buttons at the top
        with dpg.group(horizontal=True, parent="ticker_list"):
            dpg.add_button(label="Sort by Mentions", callback=lambda: sort_tickers('mentions'))
            dpg.add_button(label="Sort by Price Change", callback=lambda: sort_tickers('price_change'))
            dpg.add_button(label="Sort by Sentiment", callback=lambda: sort_tickers('sentiment_change'))
        dpg.add_separator(parent="ticker_list")
        
        # Display sorted tickers
        for ticker, data in sorted_ticker_data():
            if isinstance(data, str) and data == "Error fetching data":
                continue
                
            texture_id = f"texture_{ticker}"
            
            with dpg.tree_node(label=f"{ticker} - Mentions: {data['mentions']}", 
                             parent="ticker_list",
                             default_open=False):
                
                dpg.add_text(f"Price Change: {data['price_change']:.2f}%", 
                           color=get_color_from_percentage(data['price_change']))
                dpg.add_text(f"Sentiment Change: {data['sentiment_change']:.2f}%",
                           color=get_color_from_percentage(data['sentiment_change']))
                
                try:
                    fig = create_plot(data['prices'], data['timestamps'], ticker)
                    img_data = fig_to_rgba_array(fig)
                    
                    with dpg.texture_registry():
                        if dpg.does_item_exist(texture_id):
                            dpg.delete_item(texture_id)
                            
                        dpg.add_static_texture(
                            width=500,
                            height=300,
                            default_value=img_data,
                            tag=texture_id
                        )
                    dpg.add_image(texture_id)
                except Exception as e:
                    print(f"Error creating plot for {ticker}: {e}")
                    dpg.add_text("Error: Could not create plot")
                
    except Exception as e:
        print(f"Error refreshing UI: {e}")
        dpg.set_value("status_text", "Error updating display!")

def get_next_ticker(current_ticker):
    """Helper function to find the next ticker's row ID"""
    tickers = list(ticker_data.keys())
    try:
        current_index = tickers.index(current_ticker)
        if current_index < len(tickers) - 1:
            return f"row_{tickers[current_index + 1]}"
    except ValueError:
        pass
    return None

def create_ui():
    """Sets up the Dear PyGui interface."""
    dpg.create_context()
    
    # Create the main window with a fixed size
    with dpg.window(label="ApeWisdom Stock Sentiment", width=800, height=600, pos=(0, 0), no_move=True, no_resize=True):
        dpg.add_text("Last update: Never", tag="status_text")
        with dpg.group(horizontal=True):
            dpg.add_button(label="Manual Update", callback=update_data)
            dpg.add_loading_indicator(tag="loading_wheel", show=False, radius=2)
        
        with dpg.child_window(height=500, tag="ticker_list", autosize_x=True):
            dpg.add_text("Loading data...")
    
    # Configure and show the viewport
    dpg.create_viewport(title='Stock Sentiment Tracker', width=820, height=620)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    
    # Trigger initial data load
    update_data()
    
    # Start the main loop
    while dpg.is_dearpygui_running():
        # Update the "last update" text
        dpg.set_value("status_text", f"Last update: {get_time_since_update()}")
        dpg.render_dearpygui_frame()
    
    dpg.destroy_context()

# Run UI
if __name__ == "__main__":
    create_ui()
