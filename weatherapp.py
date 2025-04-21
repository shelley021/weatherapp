def get_weather(self):
    try:
        url = f"https://api.seniverse.com/v3/weather/daily.json?key=your_api_key&location={self.city_input.text}&language=zh-Hans&unit=c&days=1"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        result = response.text
        data = json.loads(result)
        if data.get("status") == "1000":
            weather = data["data"]["forecast"][0]
            self.weather_label.text = (
                f"{self.city_input.text} 天气:\n"
                f"天气: {weather['weather']}\n"
                f"最低温度: {weather['low']}℃\n"
                f"最高温度: {weather['high']}℃\n"
                f"风向: {weather['fengxiang']}"
            )
        else:
            self.weather_label.text = "城市不存在或输入错误"
    except Exception as e:
        self.weather_label.text = f"数据解析错误: {str(e)}"

def handle_error(self, req, error):
    self.weather_label.text = f"网络错误: {str(error)}"