from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.network.urlrequest import UrlRequest
from urllib.parse import quote
import json
import certifi

class WeatherApp(App):
    def build(self):
        self.layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        self.city_input = TextInput(
            hint_text='输入城市名',
            size_hint=(1, 0.2),
            multiline=False
        )
        self.submit = Button(
            text='查询天气',
            size_hint=(1, 0.2),
            background_normal='',
            background_color=(0.2, 0.6, 1, 1)
        )
        self.weather_label = Label(
            text='天气信息将显示在这里',
            size_hint=(1, 0.6),
            halign='center',
            valign='middle'
        )
        
        self.submit.bind(on_press=self.get_weather)
        self.layout.add_widget(self.city_input)
        self.layout.add_widget(self.submit)
        self.layout.add_widget(self.weather_label)
        return self.layout

    def get_weather(self, instance):
        city = self.city_input.text.strip()
        if not city:
            self.weather_label.text = "请输入城市名"
            return
            
        try:
            url = f'https://wthrcdn.etouch.cn/weather_mini?city={quote(city)}'
            UrlRequest(
                url, 
                on_success=self.update_ui, 
                on_error=self.handle_error,
                timeout=15,
                ca_file=certifi.where(),
                req_headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Content-Type': 'application/json'
                }
            )
            self.weather_label.text = "查询中..."
        except Exception as e:
            self.weather_label.text = f"请求错误: {str(e)}"

    def update_ui(self, req, result):
        try:
            data = json.loads(result)
            if data.get('status') == 1000:
                weather = data['data']['forecast'][0]
                self.weather_label.text = (
                    f"{self.city_input.text} 天气:\n"
                    f"{weather['type']}\n"
                    f"温度: {weather['low'][2:]}~{weather['high'][2:]}\n"
                    f"风向: {weather['fengxiang']}"
                )
            else:
                self.weather_label.text = "城市不存在或查询失败"
        except Exception as e:
            self.weather_label.text = f"数据解析错误: {str(e)}"

    def handle_error(self, req, error):
        self.weather_label.text = f"网络错误: {str(error)}"

if __name__ == '__main__':
    WeatherApp().run()

    # v1