import os
import requests
from dotenv import load_dotenv
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button

load_dotenv()
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

class WeatherApp(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding = 10
        self.spacing = 10

        self.city_input = TextInput(hint_text="Enter city (e.g., Chongqing)", size_hint=(1, 0.2))
        self.search_button = Button(text="Get Weather", size_hint=(1, 0.2))
        self.weather_label = Label(text="Weather will appear here", size_hint=(1, 0.6))

        self.search_button.bind(on_press=self.get_weather)
        self.add_widget(self.city_input)
        self.add_widget(self.search_button)
        self.add_widget(self.weather_label)

    def get_weather(self, instance):
        city = self.city_input.text.strip()
        if not city:
            self.weather_label.text = "Please enter a city!"
            return
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
        try:
            response = requests.get(url)
            data = response.json()
            if data.get("cod") != 200:
                self.weather_label.text = f"Error: {data.get('message', 'City not found')}"
                return
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"].capitalize()
            self.weather_label.text = f"{city}: {desc}, {temp}℃"
        except Exception as e:
            self.weather_label.text = f"Error: {str(e)}"

class WeatherAppMain(App):
    def build(self):
        return WeatherApp()

if __name__ == "__main__":
    WeatherAppMain().run()
