from distutils.core import setup

setup(
    name='pyualtrics',  # How you named your package folder (MyLib)
    packages=['pyualtrics'],  # Chose the same as "name"
    version='0.5',  # Start with a small number and increase it with every change you make
    license='GNU GPLv3',  # Chose a license from here: https://help.github.com/articles/licensing-a-repository
    description='Interact with Qualtrics API in Python',  # Give a short description about your library
    long_description_content_type='text/markdown',
    long_description='Full documentation available on GitHub at https://github.com/nwithan8/pyualtrics',
    author='Nate Harris',  # Type in your name
    author_email='n8gr8gbln@gmail.com',  # Type in your E-Mail
    url='https://github.com/nwithan8/pyualtrics',  # Provide either the link to your github or to your website
    download_url='https://github.com/nwithan8/pyualtrics/archive/v0.5.tar.gz',  # I explain this later on
    keywords=['Qualtrics', 'surveys', 'survey', 'API', 'automation', 'scripting'],
    # Keywords that define your package best
    install_requires=[  # I get to this in a second
        'requests',
        'pandas',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
        'Intended Audience :: Developers',  # Define that your audience are developers
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',  # Again, pick a license
        'Programming Language :: Python :: 3',  # Specify which pyhton versions that you want to support
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
)
