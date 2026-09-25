from django import forms

from .models import Comment


class CommentForm(forms.ModelForm):
    # Boş (yalnızca boşluk da) ve COMMENT_MAX_LENGTH'ten uzun yorumu reddeder.
    class Meta:
        model = Comment
        fields = ['body']
        # aria-label: sayfada çok yorum formu var, id'li <label> yerine ekran okuyucuya ad
        widgets = {'body': forms.Textarea(attrs={'rows': 3, 'aria-label': 'Yorum'})}
