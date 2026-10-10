# Exceptions

Every exception that pysportbot raises derives from `SportBotError`, and all of them can be imported from `pysportbot`.
Network errors are the one exception: they propagate as `requests.RequestException`.

```text
SportBotError
├── APIError
├── AuthenticationError
├── NotLoggedInError
├── ConfigError
├── CentreNotFoundError
├── ActivityNotFoundError
├── SlotNotFoundError
├── BookingError
│   ├── SlotAlreadyBookedError
│   ├── SlotUnavailableError
│   ├── SlotNotBookableYetError
│   └── SlotFullError
└── CancellationError
```

::: pysportbot.exceptions
    options:
      show_root_heading: false
      show_root_toc_entry: false
      show_bases: true
