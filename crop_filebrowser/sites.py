import tempfile
import urllib

from PIL import ImageFile

from django.shortcuts import render_to_response, HttpResponse, Http404
from django.template import RequestContext as Context
from django.http import HttpResponseRedirect, Http404
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.cache import never_cache

from filebrowser import sites
from filebrowser.base import FileObject
from filebrowser import functions
from filebrowser import settings as fb_settings
from django.conf import settings
from filebrowser.utils import path_strip, scale_and_crop

from forms import ImageCropDataForm

class CropFileBrowserSite(sites.FileBrowserSite):

    def get_urls(self):
        from django.conf.urls.defaults import patterns, url, include

        urlpatterns = super(CropFileBrowserSite, self).get_urls()

        urlpatterns += patterns('',
            url(r'^crop/$', self.filebrowser_view(self.crop), name="fb_crop"),
        )

        return urlpatterns

    def _get_editable_versions(self, fileobject):
        """
        Returns the version names that can be cropped.
        """

        if hasattr(settings, 'FILEBROWSER_CROP_VERSIONS'):
            return settings.FILEBROWSER_CROP_VERSIONS

        return fb_settings.ADMIN_VERSIONS

    def _do_crop(self, im, x=None, x2=None, y=None, y2=None, width=None, height=None):
        im = im.crop((x, y, x2, y2))
        x, y = [float(v) for v in im.size]
        if width:
            r = width / x
        elif height:
            r = height / y
        im = im.resize((int(x*r), int(y*r)), resample=Image.ANTIALIAS)
        return im

    def _save_crop(self, org_path, version=None, **size_args):

        tmpfile = File(NamedTemporaryFile())
        try:
            f = self.storage.open(org_path)
            im = Image.open(f)
            version_path = self.get_version_path(org_path, version)
            root, ext = os.path.splitext(version_path)
            size_args.update({
                'width' : fb_settings.VERSIONS[version].get('width'),
                'height' : fb_settings.VERSIONS[version].get('height')
            })

            im = self._do_crop(im, **size_args)
            try:
                im.save(tmpfile, format=Image.EXTENSION[ext], quality=fb_settings.VERSION_QUALITY,
                            optimize=(ext != '.gif'))
            except IOError:
                im.save(tmpfile, format=Image.EXTENSION[ext], quality=fb_settings.VERSION_QUALITY)

            # Remove the old version, if there's any
            if version_path != self.storage.get_available_name(version_path):
                self.storage.delete(version_path)
            self.storage.save(version_path, tmpfile)
        finally:
            tmpfile.close()
            try:
                f.close()
            except:
                pass
    def get_version_path(self, value, version_prefix):
        """
        Construct the PATH to an Image version.
        value has to be a path relative to the location of 
        the site's storage.
        
        version_filename = filename + version_prefix + ext
        Returns a relative path to the location of the site's storage.
        """
        
        if self.storage.isfile(value):
            path, filename = os.path.split(value)
            relative_path = path_strip(os.path.join(path,''), self.directory)
            filename, ext = os.path.splitext(filename)
            version_filename = filename + "_" + version_prefix + ext
            if fb_settings.VERSIONS_BASEDIR:
                return os.path.join(fb_settings.VERSIONS_BASEDIR, relative_path, version_filename)
            else:
                return os.path.join(self.directory, relative_path, version_filename)
        else:
            return None

    def filebrowser_view(self, view):
        "Only let staff browse the files"
        return staff_member_required(never_cache(view))

    def crop(self, request):
        """
        Crop view.
        """
        query = request.GET
        if not query.get('filename'):
            raise Http404

        path = u'%s' % os.path.join(self.directory, query.get('dir', ''))
        fileobject = FileObject(os.path.join(path, query.get('filename', '')), site=self)
        versions = self._get_editable_versions(fileobject)
        fb_settings = sites.get_settings_var(directory=self.directory)

        if not versions:
            raise Http404

        version = versions[0]
        if request.GET.get('version') and request.GET.get('version') in versions:
            version = request.GET.get('version')

        if request.POST:
            version = request.POST.get('version')
            form = ImageCropDataForm(request.POST)
            if form.is_valid():
                if version in versions:
                   self._save_crop(fileobject.path, **form.cleaned_data)
                qs = request.GET.copy()
                qs['version'] = version
                path = '%s?%s' % (request.path, qs.urlencode())
                return HttpResponseRedirect(path)
        else:
            form = ImageCropDataForm(initial={'version' : version})

        return render_to_response('cropper/crop.html', {
            'fileobject': fileobject,
            'query': query,
            'title': u'%s' % fileobject.filename,
            'breadcrumbs': sites.get_breadcrumbs(query, query.get('dir', '')),
            'breadcrumbs_title': u'%s' % fileobject.filename,
            'settings_var': fb_settings,
            'filebrowser_site': self,
            'form' : form,
            'editable_versions' : versions,
            'version' : version
        }, context_instance=Context(request, current_app=self.name))

storage = sites.storage
# Default FileBrowser site
site = CropFileBrowserSite(name='filebrowser', storage=storage)

# Default actions
from filebrowser.actions import *
site.add_action(flip_horizontal)
site.add_action(flip_vertical)
site.add_action(rotate_90_clockwise)
site.add_action(rotate_90_counterclockwise)
site.add_action(rotate_180)
