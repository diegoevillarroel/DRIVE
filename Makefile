.PHONY: install test build clean run

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v

run:
	python drive_main.py

build:
	pyinstaller drive.spec --onefile

build-dir:
	pyinstaller drive.spec --onedir

clean:
	rm -rf build/ dist/ __pycache__/ */__pycache__/ */*/__pycache__/
	rm -f *.spec
	rm -rf .pytest_cache/