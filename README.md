# Лумо / Lumo

Настольный голосовой помощник — дипломный проект на основе
[M_O](https://github.com/erlanbahtiyarov/M_O). История исходного проекта сохранена.

Разрабатываются собственный графический интерфейс, нейросетевая интерпретация
команд и питомец на рабочем столе — маленький чёрный персонаж с большими глазами.
Поддержка Linux запланирована после завершения Windows-версии.
Текущий GUI остаётся заглушкой; питомец пока не реализован.

Новая точка входа: `lumo`. Прежняя команда `voice-pc` сохранена для совместимости.
План и критерии готовности: [docs/ROADMAP.md](docs/ROADMAP.md).

Локальный модуль распознавания русскоязычных голосовых команд для управления
компьютером под Windows.

Проект включает:

- запись и распознавание речи через Faster-Whisper;
- rule-based NLU и безопасное выполнение разрешённых команд;
- нейросетевое восстановление и классификацию неточно распознанных команд;
- обучение Audio CNN по log-Mel спектрограммам;
- подготовку и валидацию размеченного датасета;
- построение графиков и метрик обучения.

Курсовые документы, отчёты, готовые изображения, веса моделей и локальное
виртуальное окружение в репозиторий не входят.

## Структура

```text
configs/                    конфигурации команд, приложений и ASR
data/                       JSON/JSONL-разметка датасетов
models/                     локальные веса моделей, исключены из Git
scripts/                    подготовка данных, обучение и построение метрик
src/voice_control_pc/       исходный код приложения
tests/                      автоматические тесты
```

Аудиофайлы корпуса из 86 записей находятся в:

```text
data/dataset_curated/audio/
```

Файл разметки:

```text
data/dataset_curated/recovery_dataset_86.jsonl
```

## Установка

Требуется Windows и Python 3.12 или новее.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,ml]"
```

## Проверка проекта

```powershell
pytest
python scripts\validate_voice_command_dataset.py `
  --dataset data\dataset_curated\recovery_dataset_86.jsonl `
  --expected-count 86
```

## Обучение моделей

Классификатор намерений по аудиосигналу:

```powershell
python scripts\train_audio_intent_classifier.py `
  --dataset data\dataset_curated\recovery_dataset_86.jsonl `
  --epochs 80 `
  --batch-size 16 `
  --augmentations 8 `
  --seed 42
```

Модель восстановления команды по ASR-тексту:

```powershell
python scripts\train_command_recovery.py `
  --dataset data\dataset_curated\recovery_dataset_86.jsonl `
  --epochs 80 `
  --batch-size 16 `
  --seed 42

python scripts\plot_command_recovery_training.py
```

Результаты обучения сохраняются локально в `models/` и `artifacts/`. Эти
каталоги исключены из Git, поскольку содержат воспроизводимые и крупные файлы.

## Запуск

Проверка текстовой команды без выполнения действия:

```powershell
voice-pc command "открой папку загрузки" --dry-run
```

Распознавание команды с микрофона:

```powershell
voice-pc listen --dry-run --duration 5
```

Графический интерфейс:

```powershell
voice-pc gui
```

Для потенциально опасных системных команд используется подтверждение
пользователя и список разрешённых действий.
