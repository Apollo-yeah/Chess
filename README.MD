# Tech Scaffold
| Type     | Tech                                                 |
|----------|------------------------------------------------------|
| Engine   | [Stockfish](https://zh.wikipedia.org/wiki/Stockfish) |
| Frontend | React.JS                                             |
| Backend  | Python Tornado                                       |

# Backend
Code by Python Tornado Web, most code is written by ChatGPT and Github Copilot. 

# Frontend
Code by React.js, most code is written by ChatGPT and Github Copilot. 

# Chess Engine
Supported By [Stockfish](https://stockfishchess.org/), a open-source engine.

Here is the [Download Page](https://stockfishchess.org/download/)

[In this case](./backend/config.py), I use the macOS, cause I use the macBook and mac-mini. 
```python
STOCKFISH_PATH = os.path.join(BASE_DIR, "stockfish/stockfish-macos-m1-apple-silicon")
```
Create a folder named 'stockfish' and take the stockfish engineer into this folder!

If you use Windows or Linux, you can visit the offical to download the suitable version and change it.