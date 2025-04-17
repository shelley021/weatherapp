y
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
import requests
from kivy.clock import Clock

class WeatherApp(App):
    def build(self):
        self.layout = BoxLayout(orientation='vertical')
        self.city_input = TextInput(hint_text='输入城市名', size_hint=(1, 0.2))
        self.submit = Button(text='查询天气', size_hint=(1, 0.2))
        self.weather_label = Label(text='天气信息将显示在这里', size_hint=(1, 0.6))
        
        self.submit.bind(on_press=self.get_weather)
        self.layout.add_widget(self.city_input)
        self.layout.add_widget(self.submit)
        self.layout.add_widget(self.weather_label)
        return self.layout

    def get_weather(self, instance):
        city = self.city_input.text
        try:
            response = requests.get(f'http://wthrcdn.etouch.cn/weather_mini?city={city}')
            data = response.json()
            if data['status'] == 1000:
                weather = data['data']['forecast'][0]
                self.weather_label.text = f"{city}天气:\n{weather['type']}\n温度: {weather['low'][2:]}~{weather['high'][2:]}"
            else:
                self.weather_label.text = "城市不存在或查询失败"
        except Exception as e:
            self.weather_label.text = f"网络错误: {str(e)}"

if __name__ == '__main__':
    WeatherApp().run()
```