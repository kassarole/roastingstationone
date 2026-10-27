from django import forms
from .models import Roast


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"multiple": True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data]
        return [single(data, initial)]


class UploadForm(forms.Form):
    alog_files = MultipleFileField(
        label=".alog files",
        help_text="Select one or more Artisan .alog files",
    )

    def clean_alog_files(self):
        files = self.cleaned_data["alog_files"]
        for f in files:
            if not f.name.lower().endswith(".alog"):
                raise forms.ValidationError(f"{f.name} is not a .alog file")
            if f.size > 10 * 1024 * 1024:
                raise forms.ValidationError(f"{f.name} exceeds 10 MB")
        return files


class NoteForm(forms.Form):
    text = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), max_length=4000)
    time_s = forms.FloatField(required=False, min_value=0)


class RoastMetaForm(forms.ModelForm):
    class Meta:
        model = Roast
        fields = [
            "title", "beans", "origin", "roast_level",
            "operator", "organization",
            "notes", "rating", "is_public",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 5}),
            "rating": forms.NumberInput(attrs={"min": 1, "max": 5}),
        }
