#!/bin/bash
export $(cat .env | xargs)
python bot.py
