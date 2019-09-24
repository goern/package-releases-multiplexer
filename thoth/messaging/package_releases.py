import faust


class PackageRelease(faust.Record):
    index_url: str
    package_name: str
    package_version: str
