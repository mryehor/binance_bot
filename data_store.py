# Общие кеши, используемые разными модулями
klines_cache = {}        # { "BTCUSDT": DataFrame, ... }
user_data_cache = {"positions": {}}  # хранит открытые позиции в DRY_RUN / real-time
