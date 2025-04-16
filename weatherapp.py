y
import os
import requests
from dotenv import load_dotenv
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button

load_dotenv('.env')
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

class WeatherApp(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding = 10
        self.spacing = 10

        self.city_input = TextInput(hint_text="Enter city (e.g., Chongqing)", multiline=False, size_hint=(1, 0.2))
        self.search_button = Button(text="Get Weather", size_hint=(1, 0.2))
        self.weather_label = Label(text="Weather will appear here", size_hint=(1, 0.6))

        self.search_button.bind(on_press=self.get_weather)
        self.add_widget(self.city_input)
        self.add_widget(self.search_button)
        self.add_widget(self.weather_label)

    def get_weather(self, instance):
        try:
            city = self.city_input.text.strip()
            if not city:
                raise ValueError("Please enter a city!")
            
            if not OPENWEATHER_API_KEY:
                raise ValueError("API key not configured in .env file!")
                
            url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("cod") != 200:
                raise ValueError(data.get('message', 'City not found'))
                
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"].capitalize()
            humidity = data["main"]["humidity"]
            wind_speed = data["wind"]["speed"]
            self.weather_label.text = f"{city}: {desc}\nTemperature: {temp}℃\nHumidity: {humidity}%\nWind: {wind_speed} m/s"
            
        except Exception as e:
            self.weather_label.text = f"Error: {str(e)}"

class WeatherAppMain(App):
    def build(self):
        return WeatherApp()

if __name__ == "__main__":
    WeatherAppMain().run()
```