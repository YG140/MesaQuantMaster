class B3ProviderError(RuntimeError):
    """Base error for B3 official-data provider failures."""


class B3DownloadError(B3ProviderError):
    """Network/transport failure while fetching an official B3 file."""


class B3ArchiveError(B3ProviderError):
    """The downloaded file is not a valid/safe archive for its expected format."""


class B3SizeLimitError(B3ProviderError):
    """Download or uncompressed size exceeded a configured safety limit."""


class B3ParseError(B3ProviderError):
    """A record could not be parsed according to the official layout."""


class B3NotConfiguredError(B3ProviderError):
    """
    The requested B3 official dataset (BVBG.186 EOD / BVBG.028 instrument
    registry) has no confirmed public, unauthenticated, deterministic URL.

    B3's own UP2DATA documentation
    (b3.com.br/en_us/market-data-and-indices/data-services/up2data/
    available-data/) classifies BVBG.186 and BVBG.028 as "Legacy Channel"
    products requiring contracted access -- unlike COTAHIST, which is
    confirmed public. This exception is raised INSTEAD OF silently
    returning empty/fabricated data, so callers can distinguish "this
    dataset is real but not configured" from "no data for this instrument".
    Never caught-and-hidden: the resolver must record it as UNAVAILABLE,
    never as a resolved value.
    """
