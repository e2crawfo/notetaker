#!/usr/bin/env python

try:
    from setuptools import setup
except ImportError:
    try:
        from ez_setup import use_setuptools
        use_setuptools()
        from setuptools import setup
    except Exception as e:
        print("Forget setuptools, trying distutils...")
        from distutils.core import setup


description = ("Simple notetaking scripts using vim.")

setup(
    name="notetaker",
    version="0.0.1",
    author="Eric Crawford",
    author_email="e2crawfo@uwaterloo.ca",
    packages=['notetaker'],
    url="https://github.com/e2crawfo/notetaker",
    description=description,
    requires=[],
    entry_points={
        'console_scripts': [
            'viewnote=notetaker:view_note_cl',
            'makenote=notetaker:make_note_cl']},
    package_data={'notetaker': ['config.ini']}
)
